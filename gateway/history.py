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


def get_entry(entry_id: str, client_id: str | None = None) -> dict[str, Any] | None:
    if hasattr(_impl(), "get_entry"):
        return _impl().get_entry(entry_id, client_id=client_id)
    return None


def apply_refine(
    entry_id: str,
    *,
    video_refined_bytes: bytes,
    wav2lip_worker_url: str,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    return _impl().apply_refine(
        entry_id,
        video_refined_bytes=video_refined_bytes,
        wav2lip_worker_url=wav2lip_worker_url,
        client_id=client_id,
    )


def get_media_bytes(
    entry_id: str,
    kind: str,
    client_id: str | None = None,
) -> bytes | None:
    if hasattr(_impl(), "get_media_bytes"):
        return _impl().get_media_bytes(entry_id, kind, client_id=client_id)
    return None


def get_video_path(entry_id: str, variant: str = "stage1"):
    impl = _impl()
    if hasattr(impl, "get_video_path"):
        return impl.get_video_path(entry_id, variant=variant)
    return impl.get_video_path(entry_id)


def get_video_file(entry_id: str, variant: str = "stage1", client_id: str | None = None):
    impl = _impl()
    if hasattr(impl, "get_video_file"):
        return impl.get_video_file(entry_id, variant=variant, client_id=client_id)
    path = get_video_path(entry_id, variant=variant)
    if path is None:
        return None
    return path.open("rb"), "filesystem"


def delete_entry(entry_id: str, client_id: str | None = None) -> bool:
    return _impl().delete_entry(entry_id, client_id=client_id)
