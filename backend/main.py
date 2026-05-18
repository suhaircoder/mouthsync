import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from config_store import get_config, save_config
from db import close_client, ensure_indexes, mongo_enabled, ping
from history import (
    apply_refine,
    delete_entry,
    get_entry,
    get_media_bytes,
    get_video_file,
    get_video_path,
    list_entries,
    save_generation,
    storage_backend,
)
from audio_prep import (
    AUDIO_PREP_VERSION,
    AudioPrepError,
    audio_prep_defaults,
    ffmpeg_available,
    resolve_audio_filename,
)
from photo_prep import FaceCheckError, photo_prep_defaults
from photo_prep import prepare_photo_baseline
from prep_pipeline import (
    _audio_mime,
    _photo_mime,
    build_audio_preview_response,
    build_photo_preview_response,
    parse_bool_form,
    parse_prep_options,
    run_audio_prep,
    run_photo_prep,
    run_prep,
)
from worker_client import post_infer, post_refine

ENV_WORKER_URL = os.environ.get("WORKER_URL", "").strip().rstrip("/")
ENV_WORKER_API_KEY = os.environ.get("WORKER_API_KEY", "").strip()
ENV_WAV2LIP_WORKER_URL = os.environ.get("WAV2LIP_WORKER_URL", "").strip().rstrip("/")
ENV_WAV2LIP_WORKER_API_KEY = os.environ.get("WAV2LIP_WORKER_API_KEY", "").strip()
REQUEST_TIMEOUT_SEC = float(os.environ.get("WORKER_TIMEOUT_SEC", "600"))


class ConfigUpdateBody(BaseModel):
    worker: dict[str, Any] | None = None
    photo: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if mongo_enabled():
        if not ping():
            raise RuntimeError("MongoDB is not reachable (check MONGODB_URI)")
        ensure_indexes()
    yield
    close_client()


app = FastAPI(title="MouthSync backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-History-Id"],
)


def _resolve_worker(
    x_worker_url: str | None = None,
    x_worker_key: str | None = None,
) -> tuple[str, str]:
    url = (x_worker_url or "").strip().rstrip("/") or ENV_WORKER_URL
    key = (x_worker_key or "").strip() or ENV_WORKER_API_KEY
    return url, key


def _resolve_wav2lip_worker(
    x_wav2lip_url: str | None = None,
    x_wav2lip_key: str | None = None,
    fallback_key: str = "",
) -> tuple[str, str]:
    url = (x_wav2lip_url or "").strip().rstrip("/") or ENV_WAV2LIP_WORKER_URL
    key = (
        (x_wav2lip_key or "").strip()
        or ENV_WAV2LIP_WORKER_API_KEY
        or fallback_key
        or ENV_WORKER_API_KEY
    )
    return url, key


def _worker_headers(api_key: str) -> dict[str, str]:
    if api_key:
        return {"X-Worker-Key": api_key}
    return {}


async def _fetch_worker_health(
    client: httpx.AsyncClient,
    worker_url: str,
    worker_key: str,
) -> tuple[int, dict[str, Any] | None, str]:
    health_url = f"{worker_url.rstrip('/')}/health"
    resp = await client.get(health_url, headers=_worker_headers(worker_key))
    body = resp.text or ""
    data: dict[str, Any] | None = None
    if resp.status_code == 200:
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            try:
                data = resp.json()
            except Exception:
                data = None
    return resp.status_code, data, body


async def _assert_wav2lip_refine_worker(
    client: httpx.AsyncClient,
    wav2lip_url: str,
    wav2lip_key: str,
) -> None:
    """Refine requires mouthsync-worker-wav2lip (/refine). SadTalker only has /infer."""
    status, data, body = await _fetch_worker_health(client, wav2lip_url, wav2lip_key)
    if status != 200:
        detail = _diagnose_worker_response(
            wav2lip_url, status, body, endpoint="health", for_refine=True
        )
        code = 502 if status >= 500 else 400
        raise HTTPException(status_code=code, detail=detail)

    backend = str((data or {}).get("backend") or "").lower()
    if backend == "sadtalker":
        raise HTTPException(
            status_code=400,
            detail=(
                "В поле «Сервер улучшения губ» указан адрес этапа 1. "
                "Для этапа 2 нужен отдельный сервер улучшения губ."
            ),
        )
    if backend and backend != "wav2lip":
        raise HTTPException(
            status_code=400,
            detail="Этот адрес не подходит для этапа 2 — нужен сервер улучшения губ.",
        )
    if not backend:
        raise HTTPException(
            status_code=400,
            detail=(
                "Этот адрес не поддерживает этап 2. "
                "Укажите URL отдельного сервера улучшения губ (образ Wav2Lip в настройках облака)."
            ),
        )
    if data and not data.get("ready", True):
        raise HTTPException(
            status_code=503,
            detail="Сервер улучшения губ ещё загружает модели. Подождите и повторите.",
        )

    await _ensure_wav2lip_refine_endpoint(client, wav2lip_url, wav2lip_key)


async def _ensure_wav2lip_refine_endpoint(
    client: httpx.AsyncClient,
    wav2lip_url: str,
    wav2lip_key: str,
) -> None:
    """Detect old Wav2Lip images deployed before POST /refine existed."""
    base = wav2lip_url.rstrip("/")
    try:
        resp = await client.get(
            f"{base}/openapi.json",
            headers=_worker_headers(wav2lip_key),
            timeout=15.0,
        )
    except httpx.RequestError:
        return

    if resp.status_code != 200:
        return

    try:
        paths = resp.json().get("paths") or {}
    except Exception:
        return

    if "/refine" in paths:
        return

    raise HTTPException(
        status_code=400,
        detail=(
            "На этом сервере нет функции улучшения губ — нужна более новая версия. "
            "Обновите образ Wav2Lip на облаке и укажите новый адрес в настройках."
        ),
    )


def _diagnose_worker_response(
    worker_url: str,
    status_code: int,
    body: str,
    *,
    endpoint: str = "health",
    for_refine: bool = False,
) -> str:
    snippet = (body or "")[:800].lower()
    wrong_service = (
        "jupyter" in snippet
        or "jupyter server" in snippet
        or "gradio" in snippet
        or "-8888." in worker_url
        or ":8888" in worker_url
    )
    if wrong_service:
        return (
            "По этому адресу открыт другой сервис, не MouthSync. "
            "В настройках облака укажите URL вашего MouthSync-сервера на порту 8000."
        )
    if status_code == 404:
        if endpoint == "refine" or for_refine:
            return (
                "Сервер не умеет улучшать губы (этап 2). "
                "Проверьте поле «Сервер улучшения губ» — нужен отдельный Wav2Lip-сервер, "
                "не тот же адрес, что для этапа 1."
            )
        return (
            "Сервер по этому адресу не найден или адрес указан неверно. "
            "Проверьте URL в настройках: порт 8000, без лишнего пути в конце."
        )
    if status_code == 524 or "error code 524" in snippet or "a timeout occurred" in snippet:
        return (
            "Превышено время ожидания ответа от облака (~100 с). "
            "Сократите аудио до 5–15 секунд для проверки или попробуйте снова позже. "
            "Генерация на сервере могла продолжиться — посмотрите логи в панели облака."
        )
    if "<html" in snippet or "<!doctype" in snippet:
        return (
            "Сервер вернул веб-страницу вместо ответа MouthSync. "
            "Проверьте адрес: нужен URL прокси на порту 8000."
        )
    if body and len(body) < 500 and "detail" not in snippet:
        return body[:500]
    return f"Ошибка связи с сервером (код {status_code}). Проверьте адрес в настройках."


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "worker_configured": bool(ENV_WORKER_URL),
        "worker_source": "env" if ENV_WORKER_URL else "ui_or_headers",
        "photo_prep": photo_prep_defaults(),
        "audio_prep": audio_prep_defaults(),
        "audio_prep_version": AUDIO_PREP_VERSION,
        "ffmpeg_available": ffmpeg_available(),
        "wav2lip_worker_configured": bool(ENV_WAV2LIP_WORKER_URL),
        "storage": storage_backend(),
        "mongodb": {
            "enabled": mongo_enabled(),
            "ok": ping() if mongo_enabled() else False,
        },
    }


@app.get("/api/photo-defaults")
def photo_defaults() -> dict:
    return photo_prep_defaults()


@app.get("/api/audio-defaults")
def audio_defaults() -> dict:
    return audio_prep_defaults()


@app.get("/api/config")
def read_config(x_client_id: str | None = Header(default=None, alias="X-Client-Id")):
    if not mongo_enabled():
        return JSONResponse(
            status_code=503,
            content={"detail": "MongoDB не настроен. Задайте MONGODB_URI."},
        )
    if not x_client_id:
        return {"worker": None, "photo": None, "audio": None, "stored": False}
    cfg = get_config(x_client_id)
    if not cfg:
        return {"worker": None, "photo": None, "audio": None, "stored": False}
    return {**cfg, "stored": True}


@app.put("/api/config")
def write_config(
    body: ConfigUpdateBody,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    if not mongo_enabled():
        raise HTTPException(status_code=503, detail="MongoDB не настроен. Задайте MONGODB_URI.")
    if not x_client_id:
        raise HTTPException(status_code=400, detail="Заголовок X-Client-Id обязателен.")
    try:
        saved = save_config(
            x_client_id,
            worker=body.worker,
            photo=body.photo,
            audio=body.audio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return saved


@app.get("/api/history")
def history_list(
    limit: int = 50,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    return {"items": list_entries(limit=min(max(limit, 1), 200), client_id=x_client_id)}


def _stream_history_video(entry_id: str, variant: str, x_client_id: str | None):
    opened = get_video_file(entry_id, variant=variant, client_id=x_client_id)
    if opened is not None:
        stream, _kind = opened

        def iter_chunks():
            try:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if hasattr(stream, "close"):
                    stream.close()

        suffix = "refined" if variant == "refined" else "stage1"
        return StreamingResponse(
            iter_chunks(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="mouthsync-{entry_id}-{suffix}.mp4"'
            },
        )

    path = get_video_path(entry_id, variant=variant)
    if path is None:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    suffix = "refined" if variant == "refined" else "stage1"
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=f"mouthsync-{entry_id}-{suffix}.mp4",
    )


@app.get("/api/history/{entry_id}/video")
def history_video_default(
    entry_id: str,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    return _stream_history_video(entry_id, "stage1", x_client_id)


@app.get("/api/history/{entry_id}/video/stage1")
def history_video_stage1(
    entry_id: str,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    return _stream_history_video(entry_id, "stage1", x_client_id)


@app.get("/api/history/{entry_id}/video/refined")
def history_video_refined(
    entry_id: str,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    return _stream_history_video(entry_id, "refined", x_client_id)


@app.post("/api/history/{entry_id}/refine")
async def history_refine(
    entry_id: str,
    x_wav2lip_worker_url: str | None = Header(default=None, alias="X-Wav2lip-Worker-Url"),
    x_wav2lip_worker_key: str | None = Header(default=None, alias="X-Wav2lip-Worker-Key"),
    x_worker_key: str | None = Header(default=None, alias="X-Worker-Key"),
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    doc = get_entry(entry_id, client_id=x_client_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if doc.get("refined"):
        raise HTTPException(status_code=409, detail="Wav2Lip уже применён к этой записи.")

    wav2lip_url, wav2lip_key = _resolve_wav2lip_worker(
        x_wav2lip_worker_url, x_wav2lip_worker_key, fallback_key=x_worker_key
    )
    if not wav2lip_url:
        raise HTTPException(
            status_code=400,
            detail="Не задан адрес сервера улучшения губ. Укажите его в настройках на странице.",
        )

    video_bytes = get_media_bytes(entry_id, "video_stage1", client_id=x_client_id)
    audio_bytes = get_media_bytes(entry_id, "audio", client_id=x_client_id)
    if not video_bytes or not audio_bytes:
        raise HTTPException(status_code=404, detail="Не найдены видео или аудио для refine.")

    audio_name = doc.get("audio_name") or "audio.wav"
    audio_mime = _audio_mime(audio_name, True)

    timeout = httpx.Timeout(REQUEST_TIMEOUT_SEC)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            await _assert_wav2lip_refine_worker(client, wav2lip_url, wav2lip_key)
            refine_resp = await post_refine(
                client,
                wav2lip_url=wav2lip_url,
                wav2lip_key=wav2lip_key,
                video_bytes=video_bytes,
                audio_name=audio_name,
                audio_bytes=audio_bytes,
                audio_mime=audio_mime,
            )
    except HTTPException:
        raise
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось связаться с сервером улучшения губ: {e}",
        ) from e

    if refine_resp.status_code != 200:
        body = refine_resp.text or ""
        detail = _diagnose_worker_response(
            wav2lip_url,
            refine_resp.status_code,
            body,
            endpoint="refine",
            for_refine=True,
        )
        status = 504 if refine_resp.status_code == 524 else refine_resp.status_code
        raise HTTPException(
            status_code=status,
            detail=detail,
        )

    meta = apply_refine(
        entry_id,
        video_refined_bytes=refine_resp.content,
        wav2lip_worker_url=wav2lip_url,
        client_id=x_client_id,
    )
    if meta is None:
        raise HTTPException(status_code=409, detail="Не удалось сохранить результат refine.")

    return Response(
        content=refine_resp.content,
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'attachment; filename="animated-refined.mp4"',
            "X-History-Id": entry_id,
            "X-Pipeline": ",".join(meta.get("pipeline") or []),
            "X-Refined": "1",
            "X-Video-Stage1-Url": meta.get("video_stage1_url") or "",
            "X-Video-Refined-Url": meta.get("video_refined_url") or "",
        },
    )


@app.delete("/api/history/{entry_id}")
def history_delete(
    entry_id: str,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    if not delete_entry(entry_id, client_id=x_client_id):
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"ok": True, "id": entry_id}


@app.get("/api/worker-status")
async def worker_status(
    x_worker_url: str | None = Header(default=None),
    x_worker_key: str | None = Header(default=None),
):
    worker_url, worker_key = _resolve_worker(x_worker_url, x_worker_key)
    if not worker_url:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "detail": "Укажите URL воркера в настройках UI или в .env (WORKER_URL).",
            },
        )

    health_url = f"{worker_url}/health"
    timeout = httpx.Timeout(30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(health_url, headers=_worker_headers(worker_key))
    except httpx.RequestError as e:
        return {
            "ok": False,
            "worker_url": worker_url,
            "detail": f"Не удалось подключиться: {e}",
        }

    if resp.status_code != 200:
        body = resp.text or ""
        return {
            "ok": False,
            "worker_url": worker_url,
            "status_code": resp.status_code,
            "detail": _diagnose_worker_response(worker_url, resp.status_code, body),
        }

    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        body = resp.text or ""
        return {
            "ok": False,
            "worker_url": worker_url,
            "status_code": resp.status_code,
            "detail": _diagnose_worker_response(worker_url, resp.status_code, body),
        }

    return {
        "ok": True,
        "worker_url": worker_url,
        "worker": resp.json(),
    }


@app.get("/api/wav2lip-worker-status")
async def wav2lip_worker_status(
    x_wav2lip_worker_url: str | None = Header(default=None, alias="X-Wav2lip-Worker-Url"),
    x_wav2lip_worker_key: str | None = Header(default=None, alias="X-Wav2lip-Worker-Key"),
    x_worker_key: str | None = Header(default=None, alias="X-Worker-Key"),
):
    wav2lip_url, wav2lip_key = _resolve_wav2lip_worker(
        x_wav2lip_worker_url, x_wav2lip_worker_key, fallback_key=(x_worker_key or "").strip()
    )
    if not wav2lip_url:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "detail": "Укажите адрес сервера улучшения губ в настройках.",
            },
        )

    health_url = f"{wav2lip_url}/health"
    timeout = httpx.Timeout(30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(health_url, headers=_worker_headers(wav2lip_key))
    except httpx.RequestError as e:
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "detail": f"Не удалось подключиться: {e}",
        }

    if resp.status_code != 200:
        body = resp.text or ""
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "status_code": resp.status_code,
            "detail": _diagnose_worker_response(wav2lip_url, resp.status_code, body),
        }

    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        body = resp.text or ""
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "status_code": resp.status_code,
            "detail": _diagnose_worker_response(wav2lip_url, resp.status_code, body),
        }

    worker = resp.json()
    backend = str(worker.get("backend") or "").lower()
    if backend == "sadtalker":
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "worker": worker,
            "detail": "Это адрес этапа 1. Для этапа 2 укажите отдельный сервер улучшения губ.",
        }
    if backend and backend != "wav2lip":
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "worker": worker,
            "detail": "Этот адрес не подходит для этапа 2.",
        }
    if not backend:
        return {
            "ok": False,
            "worker_url": wav2lip_url,
            "worker": worker,
            "detail": "Этот сервер не поддерживает этап 2. Нужен отдельный Wav2Lip-сервер.",
        }

    return {
        "ok": True,
        "worker_url": wav2lip_url,
        "worker": worker,
    }


@app.post("/api/preview-photo")
async def preview_photo(
    photo: UploadFile = File(...),
    photo_prep_enabled: str | None = Form(None),
    face_check_enabled: str | None = Form(None),
    face_require_single: str | None = Form(None),
    face_auto_crop: str | None = Form(None),
    face_align_enabled: str | None = Form(None),
    photo_max_edge: str | None = Form(None),
    face_min_size_ratio: str | None = Form(None),
    photo_brightness: str | None = Form(None),
    photo_contrast: str | None = Form(None),
    photo_sharpness: str | None = Form(None),
    photo_jpeg_quality: str | None = Form(None),
):
    photo_bytes = await photo.read()
    photo_name = photo.filename or "photo.jpg"

    photo_enabled, _, photo_opts, _ = parse_prep_options(
        photo_prep_enabled=photo_prep_enabled,
        face_check_enabled=face_check_enabled,
        face_require_single=face_require_single,
        face_auto_crop=face_auto_crop,
        face_align_enabled=face_align_enabled,
        photo_max_edge=photo_max_edge,
        face_min_size_ratio=face_min_size_ratio,
        photo_brightness=photo_brightness,
        photo_contrast=photo_contrast,
        photo_sharpness=photo_sharpness,
        photo_jpeg_quality=photo_jpeg_quality,
    )

    raw_bytes = photo_bytes
    raw_name = photo_name
    try:
        before_bytes, before_name = prepare_photo_baseline(raw_bytes, raw_name, photo_opts)
        after_bytes, after_name = run_photo_prep(
            raw_bytes, raw_name, photo_opts, enabled=photo_enabled
        )
    except FaceCheckError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return build_photo_preview_response(
        before_bytes,
        before_name,
        after_bytes,
        after_name,
        photo_opts,
        prep_enabled=photo_enabled,
    )


@app.post("/api/preview-audio")
async def preview_audio(
    audio: UploadFile = File(...),
    audio_prep_enabled: str | None = Form(None),
    audio_delay_ms: str | None = Form(None),
    audio_trim_silence: str | None = Form(None),
    audio_trim_threshold_db: str | None = Form(None),
    audio_gain_db: str | None = Form(None),
    audio_normalize_peak: str | None = Form(None),
    audio_max_duration_sec: str | None = Form(None),
    audio_sample_rate_hz: str | None = Form(None),
    audio_force_mono: str | None = Form(None),
    audio_playback_speed: str | None = Form(None),
):
    audio_bytes = await audio.read()
    audio_name = resolve_audio_filename(audio.filename, audio.content_type)

    _, audio_enabled, _, audio_opts = parse_prep_options(
        audio_prep_enabled=audio_prep_enabled,
        audio_delay_ms=audio_delay_ms,
        audio_trim_silence=audio_trim_silence,
        audio_trim_threshold_db=audio_trim_threshold_db,
        audio_gain_db=audio_gain_db,
        audio_normalize_peak=audio_normalize_peak,
        audio_max_duration_sec=audio_max_duration_sec,
        audio_sample_rate_hz=audio_sample_rate_hz,
        audio_force_mono=audio_force_mono,
        audio_playback_speed=audio_playback_speed,
    )

    raw_bytes = audio_bytes
    raw_name = audio_name
    try:
        after_bytes, after_name = run_audio_prep(
            raw_bytes, raw_name, audio_opts, enabled=audio_enabled
        )
    except AudioPrepError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return build_audio_preview_response(
        raw_bytes,
        raw_name,
        after_bytes,
        after_name,
        audio_opts,
        prep_enabled=audio_enabled,
    )


@app.post("/api/generate")
async def generate(
    photo: UploadFile = File(...),
    audio: UploadFile = File(...),
    photo_prep_enabled: str | None = Form(None),
    audio_prep_enabled: str | None = Form(None),
    face_check_enabled: str | None = Form(None),
    face_require_single: str | None = Form(None),
    face_auto_crop: str | None = Form(None),
    face_align_enabled: str | None = Form(None),
    photo_max_edge: str | None = Form(None),
    face_min_size_ratio: str | None = Form(None),
    photo_brightness: str | None = Form(None),
    photo_contrast: str | None = Form(None),
    photo_sharpness: str | None = Form(None),
    photo_jpeg_quality: str | None = Form(None),
    audio_delay_ms: str | None = Form(None),
    audio_trim_silence: str | None = Form(None),
    audio_trim_threshold_db: str | None = Form(None),
    audio_gain_db: str | None = Form(None),
    audio_normalize_peak: str | None = Form(None),
    audio_max_duration_sec: str | None = Form(None),
    audio_sample_rate_hz: str | None = Form(None),
    audio_force_mono: str | None = Form(None),
    audio_playback_speed: str | None = Form(None),
    x_worker_url: str | None = Header(default=None),
    x_worker_key: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    worker_url, worker_key = _resolve_worker(x_worker_url, x_worker_key)
    if not worker_url:
        raise HTTPException(
            status_code=503,
            detail="Не задан адрес сервера генерации. Укажите его в настройках на странице.",
        )

    photo_bytes = await photo.read()
    audio_bytes = await audio.read()
    photo_name = photo.filename or "photo.jpg"
    audio_name = resolve_audio_filename(audio.filename, audio.content_type)

    photo_enabled, audio_enabled, photo_opts, audio_opts = parse_prep_options(
        photo_prep_enabled=photo_prep_enabled,
        audio_prep_enabled=audio_prep_enabled,
        face_check_enabled=face_check_enabled,
        face_require_single=face_require_single,
        face_auto_crop=face_auto_crop,
        face_align_enabled=face_align_enabled,
        photo_max_edge=photo_max_edge,
        face_min_size_ratio=face_min_size_ratio,
        photo_brightness=photo_brightness,
        photo_contrast=photo_contrast,
        photo_sharpness=photo_sharpness,
        photo_jpeg_quality=photo_jpeg_quality,
        audio_delay_ms=audio_delay_ms,
        audio_trim_silence=audio_trim_silence,
        audio_trim_threshold_db=audio_trim_threshold_db,
        audio_gain_db=audio_gain_db,
        audio_normalize_peak=audio_normalize_peak,
        audio_max_duration_sec=audio_max_duration_sec,
        audio_sample_rate_hz=audio_sample_rate_hz,
        audio_force_mono=audio_force_mono,
        audio_playback_speed=audio_playback_speed,
    )

    try:
        photo_bytes, photo_name, audio_bytes, audio_name = run_prep(
            photo_bytes,
            photo_name,
            audio_bytes,
            audio_name,
            photo_opts,
            audio_opts,
            photo_enabled=photo_enabled,
            audio_enabled=audio_enabled,
        )
    except FaceCheckError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except AudioPrepError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    photo_mime = _photo_mime(photo_bytes, photo_name, photo_enabled)
    audio_mime = _audio_mime(audio_name, audio_enabled)

    timeout = httpx.Timeout(REQUEST_TIMEOUT_SEC)
    pipeline: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await post_infer(
                client,
                worker_url=worker_url,
                worker_key=worker_key,
                photo_name=photo_name,
                photo_bytes=photo_bytes,
                photo_mime=photo_mime,
                audio_name=audio_name,
                audio_bytes=audio_bytes,
                audio_mime=audio_mime,
            )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось связаться с сервером генерации: {e}",
        ) from e

    if resp.status_code != 200:
        body = resp.text or ""
        detail = _diagnose_worker_response(worker_url, resp.status_code, body)
        status = 504 if resp.status_code == 524 else resp.status_code
        raise HTTPException(status_code=status, detail=detail)

    pipeline.append("infer")
    video_bytes = resp.content

    meta = save_generation(
        photo_bytes=photo_bytes,
        photo_name=photo_name,
        audio_bytes=audio_bytes,
        audio_name=audio_name,
        video_bytes=video_bytes,
        client_id=x_client_id,
        worker_url=worker_url,
        pipeline=pipeline,
        photo_prep={**asdict(photo_opts), "enabled": photo_enabled},
        audio_prep={**asdict(audio_opts), "enabled": audio_enabled},
    )

    return Response(
        content=video_bytes,
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'attachment; filename="animated.mp4"',
            "X-History-Id": meta["id"],
            "X-Pipeline": ",".join(pipeline),
            "X-Stage": "1",
            "X-Video-Stage1-Url": meta.get("video_stage1_url") or "",
        },
    )
