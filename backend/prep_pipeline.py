"""Shared photo/audio prep for generate and preview."""

from __future__ import annotations

import base64
import io
import mimetypes
from dataclasses import asdict
from typing import Any

from PIL import Image

from audio_prep import (
    AudioPrepError,
    AudioPrepOptions,
    audio_duration_ms,
    options_from_form as audio_options_from_form,
    prepare_audio,
)
from photo_prep import (
    FaceCheckError,
    PhotoPrepOptions,
    options_from_form as photo_options_from_form,
    prepare_photo,
    prepare_photo_baseline,
)


def parse_bool_form(raw: str | None, default: bool = True) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_prep_options(
    *,
    photo_prep_enabled: str | None = None,
    audio_prep_enabled: str | None = None,
    face_check_enabled: str | None = None,
    face_require_single: str | None = None,
    face_auto_crop: str | None = None,
    photo_max_edge: str | None = None,
    face_min_size_ratio: str | None = None,
    photo_brightness: str | None = None,
    photo_contrast: str | None = None,
    photo_sharpness: str | None = None,
    photo_jpeg_quality: str | None = None,
    audio_delay_ms: str | None = None,
    audio_trim_silence: str | None = None,
    audio_trim_threshold_db: str | None = None,
    audio_gain_db: str | None = None,
    audio_normalize_peak: str | None = None,
    audio_max_duration_sec: str | None = None,
    audio_sample_rate_hz: str | None = None,
    audio_force_mono: str | None = None,
    audio_playback_speed: str | None = None,
) -> tuple[bool, bool, PhotoPrepOptions, AudioPrepOptions]:
    photo_enabled = parse_bool_form(photo_prep_enabled, True)
    audio_enabled = parse_bool_form(audio_prep_enabled, True)
    photo_opts = photo_options_from_form(
        face_check_enabled=face_check_enabled,
        face_require_single=face_require_single,
        face_auto_crop=face_auto_crop,
        photo_max_edge=photo_max_edge,
        face_min_size_ratio=face_min_size_ratio,
        photo_brightness=photo_brightness,
        photo_contrast=photo_contrast,
        photo_sharpness=photo_sharpness,
        photo_jpeg_quality=photo_jpeg_quality,
    )
    audio_opts = audio_options_from_form(
        audio_delay_ms=audio_delay_ms,
        audio_trim_silence=audio_trim_silence,
        audio_trim_threshold_db=audio_trim_threshold_db,
        audio_gain_db=audio_gain_db,
        audio_normalize_peak=audio_normalize_peak,
        audio_max_duration_sec=audio_max_duration_sec,
        audio_sample_rate_hz=audio_sample_rate_hz,
        audio_force_mono=audio_force_mono,
        audio_playback_speed=audio_playback_speed,
    )
    return photo_enabled, audio_enabled, photo_opts, audio_opts


def run_photo_prep(
    photo_bytes: bytes,
    photo_name: str,
    photo_opts: PhotoPrepOptions,
    *,
    enabled: bool,
) -> tuple[bytes, str]:
    if not enabled:
        return photo_bytes, photo_name
    return prepare_photo(photo_bytes, photo_name, photo_opts)


def run_audio_prep(
    audio_bytes: bytes,
    audio_name: str,
    audio_opts: AudioPrepOptions,
    *,
    enabled: bool,
) -> tuple[bytes, str]:
    if not enabled:
        return audio_bytes, audio_name
    return prepare_audio(audio_bytes, audio_name, audio_opts)


def run_prep(
    photo_bytes: bytes,
    photo_name: str,
    audio_bytes: bytes,
    audio_name: str,
    photo_opts: PhotoPrepOptions,
    audio_opts: AudioPrepOptions,
    *,
    photo_enabled: bool = True,
    audio_enabled: bool = True,
) -> tuple[bytes, str, bytes, str]:
    photo_bytes, photo_name = run_photo_prep(
        photo_bytes, photo_name, photo_opts, enabled=photo_enabled
    )
    audio_bytes, audio_name = run_audio_prep(
        audio_bytes, audio_name, audio_opts, enabled=audio_enabled
    )
    return photo_bytes, photo_name, audio_bytes, audio_name


def _photo_mime(photo_bytes: bytes, photo_name: str, processed: bool) -> str:
    if processed:
        return "image/jpeg"
    mime, _ = mimetypes.guess_type(photo_name)
    if mime and mime.startswith("image/"):
        return mime
    try:
        img = Image.open(io.BytesIO(photo_bytes))
        fmt = (img.format or "JPEG").upper()
        return Image.MIME.get(fmt, "image/jpeg")
    except Exception:
        return "image/jpeg"


def _audio_mime(audio_name: str, processed: bool) -> str:
    if processed:
        return "audio/wav"
    mime, _ = mimetypes.guess_type(audio_name)
    return mime or "application/octet-stream"


def _photo_media_dict(photo_bytes: bytes, photo_name: str, *, processed: bool) -> dict[str, Any]:
    try:
        img = Image.open(io.BytesIO(photo_bytes))
        width, height = img.size
    except Exception:
        width, height = 0, 0
    mime = _photo_mime(photo_bytes, photo_name, processed)
    photo_b64 = base64.b64encode(photo_bytes).decode("ascii")
    return {
        "filename": photo_name,
        "content_type": mime,
        "width": width,
        "height": height,
        "size_bytes": len(photo_bytes),
        "data_url": f"data:{mime};base64,{photo_b64}",
    }


def _audio_media_dict(audio_bytes: bytes, audio_name: str, *, processed: bool) -> dict[str, Any]:
    duration_ms = audio_duration_ms(audio_bytes, audio_name) if audio_bytes else 0
    mime = _audio_mime(audio_name, processed)
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    return {
        "filename": audio_name,
        "content_type": mime,
        "duration_ms": duration_ms,
        "size_bytes": len(audio_bytes),
        "data_url": f"data:{mime};base64,{audio_b64}",
    }


def build_photo_preview_response(
    before_bytes: bytes,
    before_name: str,
    after_bytes: bytes,
    after_name: str,
    photo_opts: PhotoPrepOptions,
    *,
    prep_enabled: bool,
) -> dict[str, Any]:
    return {
        "prep_enabled": prep_enabled,
        "before": _photo_media_dict(before_bytes, before_name, processed=False),
        "after": _photo_media_dict(after_bytes, after_name, processed=prep_enabled),
        "photo": _photo_media_dict(after_bytes, after_name, processed=prep_enabled),
        "photo_prep": {**asdict(photo_opts), "enabled": prep_enabled},
    }


def build_audio_preview_response(
    before_bytes: bytes,
    before_name: str,
    after_bytes: bytes,
    after_name: str,
    audio_opts: AudioPrepOptions,
    *,
    prep_enabled: bool,
) -> dict[str, Any]:
    return {
        "prep_enabled": prep_enabled,
        "before": _audio_media_dict(before_bytes, before_name, processed=False),
        "after": _audio_media_dict(after_bytes, after_name, processed=prep_enabled),
        "audio": _audio_media_dict(after_bytes, after_name, processed=prep_enabled),
        "audio_prep": {**asdict(audio_opts), "enabled": prep_enabled},
    }
