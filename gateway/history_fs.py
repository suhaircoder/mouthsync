"""Filesystem-backed generation history (fallback when MongoDB is disabled)."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

HISTORY_ROOT = Path(
    os.environ.get("HISTORY_DIR", Path(__file__).resolve().parent / "data" / "history")
)
META_FILE = "meta.json"
VIDEO_STAGE1 = "output.mp4"
VIDEO_REFINED = "output_refined.mp4"
VIDEO_RAW_LEGACY = "output_raw.mp4"
PHOTO_FILE = "photo"
AUDIO_FILE = "audio"


def ensure_history_dir() -> None:
    HISTORY_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_suffix(name: str, default: str) -> str:
    suffix = Path(name or "").suffix
    return suffix if suffix else default


def _entry_dir(entry_id: str) -> Path:
    return HISTORY_ROOT / entry_id


def _load_meta(entry_dir: Path) -> dict[str, Any] | None:
    meta_path = entry_dir / META_FILE
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_meta(entry_dir: Path, meta: dict[str, Any]) -> None:
    (entry_dir / META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _refined_path(entry_dir: Path, meta: dict[str, Any]) -> Path | None:
    refined = entry_dir / VIDEO_REFINED
    if refined.is_file():
        return refined
    raw = entry_dir / VIDEO_RAW_LEGACY
    stage1 = entry_dir / VIDEO_STAGE1
    if meta.get("refined") and raw.is_file() and stage1.is_file():
        return stage1
    return None


def _stage1_path(entry_dir: Path, meta: dict[str, Any]) -> Path | None:
    raw = entry_dir / VIDEO_RAW_LEGACY
    if raw.is_file():
        return raw
    stage1 = entry_dir / VIDEO_STAGE1
    if stage1.is_file():
        return stage1
    return None


def _entry_urls(entry_id: str, meta: dict[str, Any], entry_dir: Path) -> dict[str, str | None]:
    base = f"/api/history/{entry_id}/video"
    has_refined = _refined_path(entry_dir, meta) is not None
    return {
        "video_url": f"{base}/stage1",
        "video_stage1_url": f"{base}/stage1",
        "video_refined_url": f"{base}/refined" if has_refined else None,
    }


def save_generation(
    *,
    photo_bytes: bytes,
    photo_name: str,
    audio_bytes: bytes,
    audio_name: str,
    video_bytes: bytes,
    video_raw_bytes: bytes | None = None,
    client_id: str | None = None,
    worker_url: str = "",
    wav2lip_worker_url: str = "",
    pipeline: list[str] | None = None,
    photo_prep: dict[str, Any] | None = None,
    audio_prep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del video_raw_bytes
    ensure_history_dir()
    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + f"-{os.urandom(4).hex()}"
    entry_dir = _entry_dir(entry_id)
    entry_dir.mkdir(parents=True, exist_ok=False)

    photo_suffix = _safe_suffix(photo_name, ".jpg")
    audio_suffix = _safe_suffix(audio_name, ".wav")

    (entry_dir / f"{PHOTO_FILE}{photo_suffix}").write_bytes(photo_bytes)
    (entry_dir / f"{AUDIO_FILE}{audio_suffix}").write_bytes(audio_bytes)
    (entry_dir / VIDEO_STAGE1).write_bytes(video_bytes)

    pipe = pipeline or ["infer"]
    created_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "id": entry_id,
        "created_at": created_at,
        "photo_name": photo_name or f"photo{photo_suffix}",
        "audio_name": audio_name or f"audio{audio_suffix}",
        "client_id": client_id,
        "worker_url": worker_url,
        "wav2lip_worker_url": wav2lip_worker_url,
        "pipeline": pipe,
        "refined": False,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
    }
    _save_meta(entry_dir, meta)
    urls = _entry_urls(entry_id, meta, entry_dir)
    return {**meta, **urls}


def get_entry(entry_id: str, client_id: str | None = None) -> dict[str, Any] | None:
    if not _valid_entry_id(entry_id):
        return None
    entry_dir = _entry_dir(entry_id)
    meta = _load_meta(entry_dir)
    if not meta:
        return None
    if client_id and meta.get("client_id") and meta.get("client_id") != client_id:
        return None
    return meta


def apply_refine(
    entry_id: str,
    *,
    video_refined_bytes: bytes,
    wav2lip_worker_url: str,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    entry_dir = _entry_dir(entry_id)
    meta = get_entry(entry_id, client_id=client_id)
    if not meta:
        return None
    if _refined_path(entry_dir, meta):
        return None

    (entry_dir / VIDEO_REFINED).write_bytes(video_refined_bytes)
    pipeline = list(meta.get("pipeline") or ["infer"])
    if "wav2lip_refine" not in pipeline:
        pipeline.append("wav2lip_refine")
    meta["refined"] = True
    meta["pipeline"] = pipeline
    meta["wav2lip_worker_url"] = wav2lip_worker_url
    _save_meta(entry_dir, meta)
    urls = _entry_urls(entry_id, meta, entry_dir)
    return {**meta, **urls}


def list_entries(limit: int = 50, client_id: str | None = None) -> list[dict[str, Any]]:
    ensure_history_dir()
    entries: list[dict[str, Any]] = []
    for entry_dir in HISTORY_ROOT.iterdir():
        if not entry_dir.is_dir():
            continue
        meta = _load_meta(entry_dir)
        if not meta or _stage1_path(entry_dir, meta) is None:
            continue
        if client_id and meta.get("client_id") and meta.get("client_id") != client_id:
            continue
        entry_id = meta.get("id") or entry_dir.name
        refined = _refined_path(entry_dir, meta) is not None
        urls = _entry_urls(entry_id, meta, entry_dir)
        entries.append(
            {
                "id": entry_id,
                "created_at": meta.get("created_at", ""),
                "photo_name": meta.get("photo_name", ""),
                "audio_name": meta.get("audio_name", ""),
                "worker_url": meta.get("worker_url", ""),
                "refined": refined,
                "pipeline": meta.get("pipeline") or [],
                **urls,
            }
        )
    entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return entries[:limit]


def get_media_bytes(
    entry_id: str,
    kind: str,
    client_id: str | None = None,
) -> bytes | None:
    entry_dir = _entry_dir(entry_id)
    meta = get_entry(entry_id, client_id=client_id)
    if not meta:
        return None

    if kind == "video_stage1":
        path = _stage1_path(entry_dir, meta)
    elif kind == "video_refined":
        path = _refined_path(entry_dir, meta)
    elif kind == "photo":
        for p in entry_dir.glob(f"{PHOTO_FILE}*"):
            if p.is_file():
                return p.read_bytes()
        return None
    elif kind == "audio":
        for p in entry_dir.glob(f"{AUDIO_FILE}*"):
            if p.is_file():
                return p.read_bytes()
        return None
    else:
        return None

    return path.read_bytes() if path and path.is_file() else None


def get_video_path(entry_id: str, variant: str = "stage1") -> Path | None:
    if not _valid_entry_id(entry_id):
        return None
    entry_dir = _entry_dir(entry_id)
    meta = _load_meta(entry_dir)
    if not meta:
        return None
    if variant == "refined":
        return _refined_path(entry_dir, meta)
    return _stage1_path(entry_dir, meta)


def get_video_file(
    entry_id: str,
    variant: str = "stage1",
    client_id: str | None = None,
) -> tuple[BinaryIO, str] | None:
    path = get_video_path(entry_id, variant=variant)
    if path is None:
        return None
    if client_id:
        meta = get_entry(entry_id, client_id=client_id)
        if not meta:
            return None
    return path.open("rb"), "filesystem"


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    if not _valid_entry_id(entry_id):
        return False
    entry_dir = _entry_dir(entry_id)
    if not entry_dir.is_dir():
        return False
    if client_id:
        meta = _load_meta(entry_dir)
        if meta and meta.get("client_id") and meta.get("client_id") != client_id:
            return False
    shutil.rmtree(entry_dir)
    return True


def _valid_entry_id(entry_id: str) -> bool:
    return bool(entry_id) and ".." not in entry_id and "/" not in entry_id
