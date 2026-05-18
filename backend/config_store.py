"""Per-client settings persisted in MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import get_db, mongo_enabled


def _normalize_worker(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {
            "url": "",
            "api_key": "",
            "wav2lip_url": "",
            "wav2lip_api_key": "",
            "refine_enabled": False,
        }
    return {
        "url": (raw.get("url") or raw.get("workerUrl") or "").strip().rstrip("/"),
        "api_key": (raw.get("api_key") or raw.get("workerApiKey") or "").strip(),
        "wav2lip_url": (
            raw.get("wav2lip_url") or raw.get("wav2lipWorkerUrl") or ""
        ).strip().rstrip("/"),
        "wav2lip_api_key": (
            raw.get("wav2lip_api_key") or raw.get("wav2lipWorkerApiKey") or ""
        ).strip(),
        "refine_enabled": bool(
            raw.get("refine_enabled", raw.get("refineEnabled", False))
        ),
    }


def _normalize_audio(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    return {
        "prep_enabled": bool(raw.get("prep_enabled", raw.get("prepEnabled", True))),
        "delay_ms": int(raw.get("delay_ms", raw.get("delayMs", 0))),
        "trim_silence": bool(raw.get("trim_silence", raw.get("trimSilence", False))),
        "trim_threshold_db": float(
            raw.get("trim_threshold_db", raw.get("trimThresholdDb", -40.0))
        ),
        "gain_db": float(raw.get("gain_db", raw.get("gainDb", 0.0))),
        "normalize_peak": bool(
            raw.get("normalize_peak", raw.get("normalizePeak", False))
        ),
        "max_duration_sec": float(
            raw.get("max_duration_sec", raw.get("maxDurationSec", 0.0))
        ),
        "sample_rate_hz": int(raw.get("sample_rate_hz", raw.get("sampleRateHz", 0))),
        "force_mono": bool(raw.get("force_mono", raw.get("forceMono", True))),
        "playback_speed": float(
            raw.get("playback_speed", raw.get("playbackSpeed", 1.0))
        ),
    }


def _normalize_photo(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    return {
        "prep_enabled": bool(raw.get("prep_enabled", raw.get("prepEnabled", True))),
        "face_check_enabled": bool(
            raw.get("face_check_enabled", raw.get("faceCheckEnabled", True))
        ),
        "face_require_single": bool(
            raw.get("face_require_single", raw.get("faceRequireSingle", True))
        ),
        "face_auto_crop": bool(raw.get("face_auto_crop", raw.get("faceAutoCrop", True))),
        "max_edge_px": int(raw.get("max_edge_px", raw.get("maxEdge", 2048))),
        "min_face_size_ratio": float(
            raw.get("min_face_size_ratio", raw.get("minFaceSizeRatio", 0.12))
        ),
        "brightness": float(raw.get("brightness", 1.0)),
        "contrast": float(raw.get("contrast", 1.0)),
        "sharpness": float(raw.get("sharpness", 1.0)),
        "jpeg_quality": int(raw.get("jpeg_quality", raw.get("jpegQuality", 92))),
    }


def worker_for_api(stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "workerUrl": stored.get("url", ""),
        "workerApiKey": stored.get("api_key", ""),
        "wav2lipWorkerUrl": stored.get("wav2lip_url", ""),
        "wav2lipWorkerApiKey": stored.get("wav2lip_api_key", ""),
        "refineEnabled": bool(stored.get("refine_enabled", False)),
    }


def audio_for_api(stored: dict[str, Any]) -> dict[str, Any]:
    if not stored:
        return {}
    return {
        "prepEnabled": stored.get("prep_enabled", True),
        "delayMs": stored.get("delay_ms", 0),
        "trimSilence": stored.get("trim_silence", False),
        "trimThresholdDb": stored.get("trim_threshold_db", -40.0),
        "gainDb": stored.get("gain_db", 0.0),
        "normalizePeak": stored.get("normalize_peak", False),
        "maxDurationSec": stored.get("max_duration_sec", 0.0),
        "sampleRateHz": stored.get("sample_rate_hz", 0),
        "forceMono": stored.get("force_mono", True),
        "playbackSpeed": stored.get("playback_speed", 1.0),
    }


def photo_for_api(stored: dict[str, Any]) -> dict[str, Any]:
    if not stored:
        return {}
    return {
        "prepEnabled": stored.get("prep_enabled", True),
        "faceCheckEnabled": stored.get("face_check_enabled", True),
        "faceRequireSingle": stored.get("face_require_single", True),
        "faceAutoCrop": stored.get("face_auto_crop", True),
        "maxEdge": stored.get("max_edge_px", 2048),
        "minFaceSizeRatio": stored.get("min_face_size_ratio", 0.12),
        "brightness": stored.get("brightness", 1.0),
        "contrast": stored.get("contrast", 1.0),
        "sharpness": stored.get("sharpness", 1.0),
        "jpegQuality": stored.get("jpeg_quality", 92),
    }


def get_config(client_id: str) -> dict[str, Any] | None:
    if not mongo_enabled() or not client_id:
        return None
    doc = get_db().user_configs.find_one({"client_id": client_id}, projection={"_id": 0})
    if not doc:
        return None
    worker = doc.get("worker") or {}
    photo = doc.get("photo") or {}
    audio = doc.get("audio") or {}
    return {
        "client_id": client_id,
        "updated_at": doc.get("updated_at"),
        "worker": worker_for_api(worker),
        "photo": photo_for_api(photo),
        "audio": audio_for_api(audio),
    }


def save_config(
    client_id: str,
    *,
    worker: dict[str, Any] | None = None,
    photo: dict[str, Any] | None = None,
    audio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not mongo_enabled():
        raise RuntimeError("MongoDB is not configured")
    if not client_id:
        raise ValueError("client_id is required")

    existing = get_db().user_configs.find_one({"client_id": client_id}) or {}
    merged_worker = _normalize_worker(worker) if worker is not None else existing.get("worker", {})
    merged_photo = _normalize_photo(photo) if photo is not None else existing.get("photo", {})
    merged_audio = _normalize_audio(audio) if audio is not None else existing.get("audio", {})

    updated_at = datetime.now(timezone.utc)
    doc = {
        "client_id": client_id,
        "updated_at": updated_at,
        "worker": merged_worker,
        "photo": merged_photo,
        "audio": merged_audio,
    }
    get_db().user_configs.update_one(
        {"client_id": client_id},
        {"$set": doc},
        upsert=True,
    )
    return {
        "client_id": client_id,
        "updated_at": updated_at.isoformat(),
        "worker": worker_for_api(merged_worker),
        "photo": photo_for_api(merged_photo),
        "audio": audio_for_api(merged_audio),
    }
