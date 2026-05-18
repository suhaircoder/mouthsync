"""Render implementation for backend __BACKEND_ID__ — replace scaffold with upstream inference."""

from __future__ import annotations

BACKEND_ID = "__BACKEND_ID__"
BACKEND_READY = False
UPSTREAM_REPO = "__UPSTREAM_URL__"


def backend_info() -> dict:
    return {
        "backend": BACKEND_ID,
        "ready": BACKEND_READY,
        "upstream": UPSTREAM_REPO,
        "message": (
            f"Implement animate_face() in render.py using {UPSTREAM_REPO}. "
            "See BACKEND.md and runpod-worker-sadtalker for reference."
        ),
    }


def preload_models() -> None:
    """Optional: load weights at startup (WORKER_PRELOAD=1)."""
    if not BACKEND_READY:
        return
    # get_engine().load()


def animate_face(image_path: str, audio_path: str, output_video_path: str) -> None:
    """photo + audio → MP4. Same contract as SadTalker workers."""
    raise NotImplementedError(
        f"{BACKEND_ID}: implement inference in render.py (upstream: {UPSTREAM_REPO})"
    )
