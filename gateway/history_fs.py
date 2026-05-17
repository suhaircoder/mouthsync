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
VIDEO_FILE = "output.mp4"
PHOTO_FILE = "photo"
AUDIO_FILE = "audio"


def ensure_history_dir() -> None:
    HISTORY_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_suffix(name: str, default: str) -> str:
    suffix = Path(name or "").suffix
    return suffix if suffix else default


def save_generation(
    *,
    photo_bytes: bytes,
    photo_name: str,
    audio_bytes: bytes,
    audio_name: str,
    video_bytes: bytes,
    client_id: str | None = None,
    worker_url: str = "",
    photo_prep: dict[str, Any] | None = None,
    audio_prep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_history_dir()
    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + f"-{os.urandom(4).hex()}"
    entry_dir = HISTORY_ROOT / entry_id
    entry_dir.mkdir(parents=True, exist_ok=False)

    photo_suffix = _safe_suffix(photo_name, ".jpg")
    audio_suffix = _safe_suffix(audio_name, ".wav")

    (entry_dir / f"{PHOTO_FILE}{photo_suffix}").write_bytes(photo_bytes)
    (entry_dir / f"{AUDIO_FILE}{audio_suffix}").write_bytes(audio_bytes)
    (entry_dir / VIDEO_FILE).write_bytes(video_bytes)

    created_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "id": entry_id,
        "created_at": created_at,
        "photo_name": photo_name or f"photo{photo_suffix}",
        "audio_name": audio_name or f"audio{audio_suffix}",
        "client_id": client_id,
        "worker_url": worker_url,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
    }
    (entry_dir / META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def _load_meta(entry_dir: Path) -> dict[str, Any] | None:
    meta_path = entry_dir / META_FILE
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_entries(limit: int = 50, client_id: str | None = None) -> list[dict[str, Any]]:
    ensure_history_dir()
    entries: list[dict[str, Any]] = []
    for entry_dir in HISTORY_ROOT.iterdir():
        if not entry_dir.is_dir():
            continue
        meta = _load_meta(entry_dir)
        if not meta or not (entry_dir / VIDEO_FILE).exists():
            continue
        if client_id and meta.get("client_id") and meta.get("client_id") != client_id:
            continue
        entry_id = meta.get("id") or entry_dir.name
        entries.append(
            {
                "id": entry_id,
                "created_at": meta.get("created_at", ""),
                "photo_name": meta.get("photo_name", ""),
                "audio_name": meta.get("audio_name", ""),
                "video_url": f"/api/history/{entry_id}/video",
                "worker_url": meta.get("worker_url", ""),
            }
        )
    entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return entries[:limit]


def get_video_path(entry_id: str) -> Path | None:
    if not _valid_entry_id(entry_id):
        return None
    video_path = HISTORY_ROOT / entry_id / VIDEO_FILE
    if video_path.is_file():
        return video_path
    return None


def get_video_file(entry_id: str, client_id: str | None = None) -> tuple[BinaryIO, str] | None:
    path = get_video_path(entry_id)
    if path is None:
        return None
    return path.open("rb"), "filesystem"


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    if not _valid_entry_id(entry_id):
        return False
    entry_dir = HISTORY_ROOT / entry_id
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
