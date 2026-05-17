"""MouthSync worker API — copy from _template when adding a new backend."""

import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from render import animate_face, backend_info, preload_models

TEMP_DIR = Path(__file__).resolve().parent / "temp_files"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("WORKER_API_KEY", "").strip()
PRELOAD = os.environ.get("WORKER_PRELOAD", "0").strip().lower() in ("1", "true", "yes")


def _require_key(x_worker_key: str | None = Header(default=None)) -> None:
    if not API_KEY:
        return
    if x_worker_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Worker-Key")


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if PRELOAD:
        try:
            preload_models()
        except Exception as e:
            print(f"[worker] preload failed: {e}", flush=True)
    yield


app = FastAPI(title="MouthSync worker (livetalking)", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    info = backend_info()
    status = "ok" if info.get("ready") else "scaffold"
    return {"status": status, **info}


@app.post("/infer")
async def infer(
    background_tasks: BackgroundTasks,
    photo: UploadFile = File(...),
    audio: UploadFile = File(...),
    _: None = Depends(_require_key),
):
    info = backend_info()
    if not info.get("ready"):
        raise HTTPException(
            status_code=501,
            detail=info.get(
                "message",
                f"Backend '{info.get('backend')}' is not implemented yet. See BACKEND.md in worker directory.",
            ),
        )

    job = uuid.uuid4().hex
    photo_path = TEMP_DIR / f"{job}_photo{Path(photo.filename or '').suffix or '.jpg'}"
    audio_path = TEMP_DIR / f"{job}_audio{Path(audio.filename or '').suffix or '.wav'}"
    out_path = TEMP_DIR / f"{job}_out.mp4"

    try:
        with photo_path.open("wb") as f:
            shutil.copyfileobj(photo.file, f)
        with audio_path.open("wb") as f:
            shutil.copyfileobj(audio.file, f)

        animate_face(str(photo_path), str(audio_path), str(out_path))
        background_tasks.add_task(_safe_unlink, out_path)
        return FileResponse(
            path=str(out_path),
            media_type="video/mp4",
            filename="animated.mp4",
        )
    except ValueError as e:
        _safe_unlink(out_path)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        _safe_unlink(out_path)
        raise HTTPException(status_code=501, detail=str(e)) from e
    except Exception as e:
        _safe_unlink(out_path)
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        photo.file.close()
        audio.file.close()
        for p in (photo_path, audio_path):
            _safe_unlink(p)
