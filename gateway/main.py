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
from history import delete_entry, get_video_file, get_video_path, list_entries, save_generation, storage_backend
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
    parse_prep_options,
    run_audio_prep,
    run_photo_prep,
    run_prep,
)

ENV_WORKER_URL = os.environ.get("WORKER_URL", "").strip().rstrip("/")
ENV_WORKER_API_KEY = os.environ.get("WORKER_API_KEY", "").strip()
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


app = FastAPI(title="MouthSync gateway", lifespan=lifespan)

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


def _worker_headers(api_key: str) -> dict[str, str]:
    if api_key:
        return {"X-Worker-Key": api_key}
    return {}


def _diagnose_worker_response(worker_url: str, status_code: int, body: str) -> str:
    snippet = (body or "")[:800].lower()
    if "jupyter" in snippet or "jupyter server" in snippet:
        port_hint = ""
        if "-8888." in worker_url or ":8888" in worker_url:
            port_hint = " Похоже, открыт порт 8888 (Jupyter), а нужен HTTP-порт воркера MouthSync (обычно 8000)."
        return (
            "По этому URL отвечает Jupyter, а не MouthSync worker. "
            "Поднимите Pod с образом mouthsync-worker и Expose HTTP port 8000."
            + port_hint
        )
    if status_code == 404:
        return (
            "Эндпоинт /health не найден (404). URL должен вести на наш FastAPI-воркер "
            "(docker.io/<user>/mouthsync-worker), не на шаблон RunPod с Jupyter/Gradio."
        )
    if status_code == 524 or "error code 524" in snippet or "a timeout occurred" in snippet:
        return (
            "Таймаут HTTP-прокси RunPod (Cloudflare 524, ~100 с). SadTalker/Wav2Lip могут работать дольше — "
            "соединение оборвалось до ответа воркера. Сократите аудио (5–15 с для теста), "
            "используйте lite-воркер для длинных роликов или поднимите воркер без прокси RunPod "
            "(TCP/другой хостинг). Воркер на Pod мог продолжить рендер — проверьте Logs Pod."
        )
    if "<html" in snippet or "<!doctype" in snippet:
        return (
            "Сервис вернул HTML вместо JSON API. Проверьте URL и порт прокси RunPod "
            "(для нашего воркера — 8000, путь /health)."
        )
    return body[:500] if body else f"HTTP {status_code}"


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


@app.get("/api/history/{entry_id}/video")
def history_video(
    entry_id: str,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
):
    opened = get_video_file(entry_id, client_id=x_client_id)
    if opened is not None:
        stream, kind = opened

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

        return StreamingResponse(
            iter_chunks(),
            media_type="video/mp4",
            headers={"Content-Disposition": f'inline; filename="mouthsync-{entry_id}.mp4"'},
        )

    path = get_video_path(entry_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=f"mouthsync-{entry_id}.mp4",
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


@app.post("/api/preview-photo")
async def preview_photo(
    photo: UploadFile = File(...),
    photo_prep_enabled: str | None = Form(None),
    face_check_enabled: str | None = Form(None),
    face_require_single: str | None = Form(None),
    face_auto_crop: str | None = Form(None),
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
            detail="WORKER_URL не задан. Укажите URL RunPod в настройках на странице или в .env.",
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

    files = {
        "photo": (photo_name, photo_bytes, photo_mime),
        "audio": (audio_name, audio_bytes, audio_mime),
    }

    infer_url = f"{worker_url}/infer"
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SEC)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                infer_url,
                files=files,
                headers=_worker_headers(worker_key),
            )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось связаться с воркером {infer_url}: {e}",
        ) from e

    if resp.status_code != 200:
        body = resp.text or ""
        detail = _diagnose_worker_response(worker_url, resp.status_code, body)
        status = 504 if resp.status_code == 524 else resp.status_code
        raise HTTPException(status_code=status, detail=detail)

    video_bytes = resp.content
    meta = save_generation(
        photo_bytes=photo_bytes,
        photo_name=photo_name,
        audio_bytes=audio_bytes,
        audio_name=audio_name,
        video_bytes=video_bytes,
        client_id=x_client_id,
        worker_url=worker_url,
        photo_prep={**asdict(photo_opts), "enabled": photo_enabled},
        audio_prep={**asdict(audio_opts), "enabled": audio_enabled},
    )

    return Response(
        content=video_bytes,
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'attachment; filename="animated.mp4"',
            "X-History-Id": meta["id"],
        },
    )
