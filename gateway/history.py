"""Generation history — MongoDB (preferred) or local filesystem."""

from __future__ import annotations

from typing import Any

from db import mongo_enabled


def _impl():
    if mongo_enabled():
        import history_mongo as backend

        return backend
    import history_fs as backend

    return backend


def storage_backend() -> str:
    return "mongodb" if mongo_enabled() else "filesystem"


def save_generation(**kwargs: Any) -> dict[str, Any]:
    return _impl().save_generation(**kwargs)


def list_entries(limit: int = 50, client_id: str | None = None) -> list[dict[str, Any]]:
    return _impl().list_entries(limit=limit, client_id=client_id)


def get_video_path(entry_id: str):
    return _impl().get_video_path(entry_id)


def get_video_file(entry_id: str, client_id: str | None = None):
    if hasattr(_impl(), "get_video_file"):
        return _impl().get_video_file(entry_id, client_id=client_id)
    path = get_video_path(entry_id)
    if path is None:
        return None
    return path.open("rb"), "filesystem"


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    return _impl().delete_entry(entry_id, client_id=client_id)
