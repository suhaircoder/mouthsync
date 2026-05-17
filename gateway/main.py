import os

import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from history import delete_entry, get_video_path, list_entries, save_generation

ENV_WORKER_URL = os.environ.get("WORKER_URL", "").strip().rstrip("/")
ENV_WORKER_API_KEY = os.environ.get("WORKER_API_KEY", "").strip()
REQUEST_TIMEOUT_SEC = float(os.environ.get("WORKER_TIMEOUT_SEC", "600"))

app = FastAPI(title="MouthSync gateway")

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
            port_hint = " Port 8888 (Jupyter) may be exposed; MouthSync worker needs HTTP port 8000."
        return (
            "This URL serves Jupyter, not a MouthSync worker. "
            "Deploy a Pod with image mouthsync-worker and Expose HTTP port 8000."
            + port_hint
        )
    if status_code == 404:
        return (
            "/health not found (404). URL must point to our FastAPI worker "
            "(docker.io/<user>/mouthsync-worker), not a RunPod Jupyter/Gradio template."
        )
    if status_code == 524 or "error code 524" in snippet or "a timeout occurred" in snippet:
        return (
            "RunPod HTTP proxy timeout (Cloudflare 524, ~100s). SadTalker/Wav2Lip can take longer — "
            "the connection closed before the worker responded. Use shorter audio (5–15s for tests), "
            "try the lite worker for long clips, or host the worker without RunPod HTTP proxy "
            "(TCP/other hosting). The Pod worker may still be rendering — check Pod Logs."
        )
    if "<html" in snippet or "<!doctype" in snippet:
        return (
            "Service returned HTML instead of JSON API. Check URL and RunPod proxy port "
            "(port 8000 for our worker, path /health)."
        )
    return body[:500] if body else f"HTTP {status_code}"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "worker_configured": bool(ENV_WORKER_URL),
        "worker_source": "env" if ENV_WORKER_URL else "ui_or_headers",
    }


@app.get("/api/history")
def history_list(limit: int = 50) -> dict:
    return {"items": list_entries(limit=min(max(limit, 1), 200))}


@app.get("/api/history/{entry_id}/video")
def history_video(entry_id: str):
    path = get_video_path(entry_id)
    if path is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=f"mouthsync-{entry_id}.mp4",
    )


@app.delete("/api/history/{entry_id}")
def history_delete(entry_id: str) -> dict:
    if not delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="History entry not found")
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
                "detail": "Set worker URL in UI settings or in .env (WORKER_URL).",
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
            "detail": f"Could not connect: {e}",
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


@app.post("/api/generate")
async def generate(
    photo: UploadFile = File(...),
    audio: UploadFile = File(...),
    x_worker_url: str | None = Header(default=None),
    x_worker_key: str | None = Header(default=None),
):
    worker_url, worker_key = _resolve_worker(x_worker_url, x_worker_key)
    if not worker_url:
        raise HTTPException(
            status_code=503,
            detail="WORKER_URL is not set. Enter RunPod URL in page settings or in .env.",
        )

    photo_bytes = await photo.read()
    audio_bytes = await audio.read()
    photo_name = photo.filename or "photo.jpg"
    audio_name = audio.filename or "audio.wav"

    files = {
        "photo": (photo_name, photo_bytes, photo.content_type or "application/octet-stream"),
        "audio": (audio_name, audio_bytes, audio.content_type or "application/octet-stream"),
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
            detail=f"Cannot reach worker at {infer_url}: {e}",
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
    )

    return Response(
        content=video_bytes,
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'attachment; filename="animated.mp4"',
            "X-History-Id": meta["id"],
        },
    )
