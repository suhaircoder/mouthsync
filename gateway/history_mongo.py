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


def _stage1_file_id(doc: dict[str, Any]) -> Any | None:
    if doc.get("video_refined_file_id"):
        return doc.get("video_file_id")
    if doc.get("video_raw_file_id"):
        return doc["video_raw_file_id"]
    return doc.get("video_file_id")


def _refined_file_id(doc: dict[str, Any]) -> Any | None:
    if doc.get("video_refined_file_id"):
        return doc["video_refined_file_id"]
    if doc.get("refined") and doc.get("video_raw_file_id"):
        return doc.get("video_file_id")
    return None


def _entry_urls(entry_id: str, doc: dict[str, Any]) -> dict[str, str | None]:
    base = f"/api/history/{entry_id}/video"
    refined = _refined_file_id(doc)
    return {
        "video_url": f"{base}/stage1",
        "video_stage1_url": f"{base}/stage1",
        "video_refined_url": f"{base}/refined" if refined else None,
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
    del video_raw_bytes  # stage-1 only; refine stored via apply_refine
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
        filename="output_stage1.mp4",
        metadata={**file_meta, "kind": "video_stage1"},
    )

    pipe = pipeline or ["infer"]
    created_at = datetime.now(timezone.utc)
    doc = {
        "id": entry_id,
        "created_at": created_at,
        "photo_name": photo_name,
        "audio_name": audio_name,
        "client_id": client_id,
        "worker_url": worker_url,
        "wav2lip_worker_url": wav2lip_worker_url,
        "pipeline": pipe,
        "refined": False,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
        "photo_file_id": photo_file_id,
        "audio_file_id": audio_file_id,
        "video_file_id": video_file_id,
        "video_refined_file_id": None,
    }
    get_db().generations.insert_one(doc)

    urls = _entry_urls(entry_id, doc)
    return {
        "id": entry_id,
        "created_at": created_at.isoformat(),
        "photo_name": photo_name,
        "audio_name": audio_name,
        "client_id": client_id,
        "worker_url": worker_url,
        "wav2lip_worker_url": wav2lip_worker_url,
        "pipeline": pipe,
        "refined": False,
        "photo_prep": photo_prep or {},
        "audio_prep": audio_prep or {},
        **urls,
    }


def _entry_query(entry_id: str, client_id: str | None) -> dict[str, Any]:
    q: dict[str, Any] = {"id": entry_id}
    if client_id:
        q["client_id"] = client_id
    return q


def get_entry(entry_id: str, client_id: str | None = None) -> dict[str, Any] | None:
    if not _valid_entry_id(entry_id):
        return None
    doc = get_db().generations.find_one(_entry_query(entry_id, client_id))
    if not doc:
        return None
    return doc


def apply_refine(
    entry_id: str,
    *,
    video_refined_bytes: bytes,
    wav2lip_worker_url: str,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    doc = get_entry(entry_id, client_id=client_id)
    if not doc:
        return None
    if _refined_file_id(doc):
        return None

    fs = get_gridfs()
    file_meta = {"entry_id": entry_id, "client_id": doc.get("client_id")}
    video_refined_file_id = fs.put(
        video_refined_bytes,
        filename="output_refined.mp4",
        metadata={**file_meta, "kind": "video_refined"},
    )

    pipeline = list(doc.get("pipeline") or ["infer"])
    if "wav2lip_refine" not in pipeline:
        pipeline.append("wav2lip_refine")

    get_db().generations.update_one(
        {"id": entry_id},
        {
            "$set": {
                "video_refined_file_id": video_refined_file_id,
                "refined": True,
                "pipeline": pipeline,
                "wav2lip_worker_url": wav2lip_worker_url,
            }
        },
    )

    updated = get_entry(entry_id, client_id=client_id) or doc
    created = updated.get("created_at")
    if isinstance(created, datetime):
        created_at = created.isoformat()
    else:
        created_at = str(created or "")

    urls = _entry_urls(entry_id, updated)
    return {
        "id": entry_id,
        "created_at": created_at,
        "photo_name": updated.get("photo_name", ""),
        "audio_name": updated.get("audio_name", ""),
        "refined": True,
        "pipeline": pipeline,
        **urls,
    }


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
        urls = _entry_urls(entry_id, doc)
        items.append(
            {
                "id": entry_id,
                "created_at": created_at,
                "photo_name": doc.get("photo_name", ""),
                "audio_name": doc.get("audio_name", ""),
                "worker_url": doc.get("worker_url", ""),
                "refined": bool(_refined_file_id(doc)),
                "pipeline": doc.get("pipeline") or [],
                **urls,
            }
        )
    return items


def get_media_bytes(
    entry_id: str,
    kind: str,
    client_id: str | None = None,
) -> bytes | None:
    doc = get_entry(entry_id, client_id=client_id)
    if not doc:
        return None

    fs = get_gridfs()
    if kind == "photo":
        file_id = doc.get("photo_file_id")
    elif kind == "audio":
        file_id = doc.get("audio_file_id")
    elif kind == "video_stage1":
        file_id = _stage1_file_id(doc)
    elif kind == "video_refined":
        file_id = _refined_file_id(doc)
    else:
        return None

    if file_id is None:
        return None
    try:
        return fs.get(file_id).read()
    except Exception:
        return None


def get_video_file(
    entry_id: str,
    variant: str = "stage1",
    client_id: str | None = None,
) -> tuple[Any, str] | None:
    if not _valid_entry_id(entry_id):
        return None
    doc = get_entry(entry_id, client_id=client_id)
    if not doc:
        return None

    if variant == "refined":
        file_id = _refined_file_id(doc)
    else:
        file_id = _stage1_file_id(doc)

    if file_id is None:
        return None
    try:
        return get_gridfs().get(file_id), "gridfs"
    except Exception:
        return None


def get_video_path(entry_id: str, variant: str = "stage1") -> None:
    """Not used for MongoDB storage."""
    return None


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    if not _valid_entry_id(entry_id):
        return False
    doc = get_entry(entry_id, client_id=client_id)
    if not doc:
        return False

    fs = get_gridfs()
    for key in (
        "photo_file_id",
        "audio_file_id",
        "video_file_id",
        "video_refined_file_id",
        "video_raw_file_id",
    ):
        file_id = doc.get(key)
        if file_id is not None:
            try:
                fs.delete(file_id)
            except Exception:
                pass

    get_db().generations.delete_one({"id": entry_id})
    return True
