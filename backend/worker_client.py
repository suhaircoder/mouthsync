"""HTTP calls to MouthSync GPU workers (infer + Wav2Lip refine)."""

from __future__ import annotations

import httpx


async def post_infer(
    client: httpx.AsyncClient,
    *,
    worker_url: str,
    worker_key: str,
    photo_name: str,
    photo_bytes: bytes,
    photo_mime: str,
    audio_name: str,
    audio_bytes: bytes,
    audio_mime: str,
) -> httpx.Response:
    infer_url = f"{worker_url.rstrip('/')}/infer"
    files = {
        "photo": (photo_name, photo_bytes, photo_mime),
        "audio": (audio_name, audio_bytes, audio_mime),
    }
    return await client.post(infer_url, files=files, headers=_worker_headers(worker_key))


async def post_refine(
    client: httpx.AsyncClient,
    *,
    wav2lip_url: str,
    wav2lip_key: str,
    video_bytes: bytes,
    audio_name: str,
    audio_bytes: bytes,
    audio_mime: str,
) -> httpx.Response:
    refine_url = f"{wav2lip_url.rstrip('/')}/refine"
    files = {
        "video": ("input.mp4", video_bytes, "video/mp4"),
        "audio": (audio_name, audio_bytes, audio_mime),
    }
    return await client.post(refine_url, files=files, headers=_worker_headers(wav2lip_key))


def _worker_headers(api_key: str) -> dict[str, str]:
    if api_key:
        return {"X-Worker-Key": api_key}
    return {}
