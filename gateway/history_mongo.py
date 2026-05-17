"""MongoDB + GridFS generation history."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from db import get_db, get_gridfs


def _new_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + f"-{os.urandom(4).hex()}"


def _valid_entry_id(entry_id: str) -> bool:
    return bool(entry_id) and ".." not in entry_id and "/" not in entry_id


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
    entry_id = _new_id()
    fs = get_gridfs()
    file_meta = {"entry_id": entry_id, "client_id": client_id}

    photo_file_id = fs.put(
        photo_bytes,
        filename=photo_name or "photo.jpg",
        metadata={**file_meta, "kind": "photo"},
    )
    audio_file_id = fs.put(
        audio_bytes,
        filename=audio_name or "audio.wav",
        metadata={**file_meta, "kind": "audio"},
    )
    video_file_id = fs.put(
        video_bytes,
        filename="output.mp4",
        metadata={**file_meta, "kind": "video"},
    )

    created_at = datetime.now(timezone.utc)
    doc = {
        "id": entry_id,
        "created_at": created_at,
        "photo_name": photo_name,
        "audio_name": audio_name,
        "client_id": client_id,
        "worker_url": worker_url,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
        "photo_file_id": photo_file_id,
        "audio_file_id": audio_file_id,
        "video_file_id": video_file_id,
    }
    get_db().generations.insert_one(doc)

    return {
        "id": entry_id,
        "created_at": created_at.isoformat(),
        "photo_name": photo_name,
        "audio_name": audio_name,
        "client_id": client_id,
        "worker_url": worker_url,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
    }


def _entry_query(entry_id: str, client_id: str | None) -> dict[str, Any]:
    q: dict[str, Any] = {"id": entry_id}
    if client_id:
        q["client_id"] = client_id
    return q


def list_entries(limit: int = 50, client_id: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if client_id:
        query["client_id"] = client_id

    cursor = (
        get_db()
        .generations.find(query, projection={"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for doc in cursor:
        entry_id = doc.get("id", "")
        created = doc.get("created_at")
        if isinstance(created, datetime):
            created_at = created.isoformat()
        else:
            created_at = str(created or "")
        items.append(
            {
                "id": entry_id,
                "created_at": created_at,
                "photo_name": doc.get("photo_name", ""),
                "audio_name": doc.get("audio_name", ""),
                "video_url": f"/api/history/{entry_id}/video",
                "worker_url": doc.get("worker_url", ""),
            }
        )
    return items


def get_video_file(entry_id: str, client_id: str | None = None) -> tuple[Any, str] | None:
    if not _valid_entry_id(entry_id):
        return None
    doc = get_db().generations.find_one(_entry_query(entry_id, client_id))
    if not doc:
        return None
    try:
        return get_gridfs().get(doc["video_file_id"]), "gridfs"
    except Exception:
        return None


def get_video_path(entry_id: str) -> None:
    """Not used for MongoDB storage."""
    return None


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    if not _valid_entry_id(entry_id):
        return False
    doc = get_db().generations.find_one(_entry_query(entry_id, client_id))
    if not doc:
        return False

    fs = get_gridfs()
    for key in ("photo_file_id", "audio_file_id", "video_file_id"):
        file_id = doc.get(key)
        if file_id is not None:
            try:
                fs.delete(file_id)
            except Exception:
                pass

    get_db().generations.delete_one({"id": entry_id})
    return True
