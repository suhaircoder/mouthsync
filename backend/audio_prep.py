"""Audio normalization and tweaks before the worker."""

from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from typing import Any

import imageio_ffmpeg
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

log = logging.getLogger(__name__)

# Bump when decode pipeline changes (check GET /health → audio_prep_version).
AUDIO_PREP_VERSION = 3

_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
AudioSegment.converter = _ffmpeg


def ffmpeg_available() -> bool:
    return bool(_ffmpeg) and os.path.isfile(_ffmpeg)

_EXT_FORMAT: dict[str, str] = {
    "wav": "wav",
    "wave": "wav",
    "mp3": "mp3",
    "mpeg": "mp3",
    "mpga": "mp3",
    "m4a": "mp4",
    "mp4": "mp4",
    "aac": "aac",
    "m4b": "mp4",
    "m4p": "mp4",
    "ogg": "ogg",
    "oga": "ogg",
    "opus": "ogg",
    "flac": "flac",
    "webm": "matroska",
    "weba": "matroska",
    "mkv": "matroska",
    "mov": "mov",
    "3gp": "3gp",
    "amr": "amr",
    "wma": "asf",
    "caf": "caf",
    "aif": "aiff",
    "aiff": "aiff",
    "aifc": "aiff",
}

_SUFFIX_FOR_FMT: dict[str, str] = {
    "wav": ".wav",
    "mp3": ".mp3",
    "mp4": ".m4a",
    "ogg": ".ogg",
    "flac": ".flac",
    "matroska": ".webm",
    "mov": ".mov",
    "3gp": ".3gp",
    "amr": ".amr",
    "asf": ".wma",
    "aac": ".aac",
    "caf": ".caf",
    "aiff": ".aiff",
}


class AudioPrepError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class AudioPrepOptions:
    delay_ms: int = 0
    trim_silence: bool = False
    trim_threshold_db: float = -40.0
    gain_db: float = 0.0
    normalize_peak: bool = False
    max_duration_sec: float = 0.0
    sample_rate_hz: int = 0
    force_mono: bool = True
    playback_speed: float = 1.0


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def defaults_from_env() -> AudioPrepOptions:
    return AudioPrepOptions(
        delay_ms=_env_int("AUDIO_DELAY_MS", 0),
        trim_silence=_env_flag("AUDIO_TRIM_SILENCE"),
        trim_threshold_db=_env_float("AUDIO_TRIM_THRESHOLD_DB", -40.0),
        gain_db=_env_float("AUDIO_GAIN_DB", 0.0),
        normalize_peak=_env_flag("AUDIO_NORMALIZE_PEAK"),
        max_duration_sec=_env_float("AUDIO_MAX_DURATION_SEC", 0.0),
        sample_rate_hz=_env_int("AUDIO_SAMPLE_RATE_HZ", 0),
        force_mono=_env_flag("AUDIO_FORCE_MONO", "1"),
        playback_speed=_env_float("AUDIO_PLAYBACK_SPEED", 1.0),
    )


def audio_prep_defaults() -> dict[str, Any]:
    return asdict(defaults_from_env())


def _parse_bool(raw: str | None, fallback: bool) -> bool:
    if raw is None or raw == "":
        return fallback
    return raw.strip().lower() in ("1", "true", "yes", "on")


def options_from_form(
    *,
    audio_delay_ms: str | None = None,
    audio_trim_silence: str | None = None,
    audio_trim_threshold_db: str | None = None,
    audio_gain_db: str | None = None,
    audio_normalize_peak: str | None = None,
    audio_max_duration_sec: str | None = None,
    audio_sample_rate_hz: str | None = None,
    audio_force_mono: str | None = None,
    audio_playback_speed: str | None = None,
) -> AudioPrepOptions:
    base = defaults_from_env()

    def _int(raw: str | None, fallback: int, low: int, high: int) -> int:
        if raw is None or raw.strip() == "":
            return fallback
        try:
            return int(_clamp(float(raw), low, high))
        except ValueError:
            return fallback

    def _float(raw: str | None, fallback: float, low: float, high: float) -> float:
        if raw is None or raw.strip() == "":
            return fallback
        try:
            return _clamp(float(raw), low, high)
        except ValueError:
            return fallback

    return AudioPrepOptions(
        delay_ms=_int(audio_delay_ms, base.delay_ms, 0, 10_000),
        trim_silence=_parse_bool(audio_trim_silence, base.trim_silence),
        trim_threshold_db=_float(audio_trim_threshold_db, base.trim_threshold_db, -60.0, -20.0),
        gain_db=_float(audio_gain_db, base.gain_db, -24.0, 24.0),
        normalize_peak=_parse_bool(audio_normalize_peak, base.normalize_peak),
        max_duration_sec=_float(audio_max_duration_sec, base.max_duration_sec, 0.0, 600.0),
        sample_rate_hz=_int(audio_sample_rate_hz, base.sample_rate_hz, 0, 48_000),
        force_mono=_parse_bool(audio_force_mono, base.force_mono),
        playback_speed=_float(audio_playback_speed, base.playback_speed, 0.5, 1.5),
    )


_MIME_TO_EXT: dict[str, str] = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
    "video/mp4": ".m4a",
}


def resolve_audio_filename(name: str | None, content_type: str | None = None) -> str:
    """Ensure filename has a useful extension for ffmpeg/pydub."""
    raw = (name or "audio").strip() or "audio"
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in base:
        return base
    ct = (content_type or "").split(";")[0].strip().lower()
    ext = _MIME_TO_EXT.get(ct, ".audio")
    return f"{base}{ext}"


def _format_from_filename(filename: str) -> str | None:
    if not filename:
        return None
    base = filename.split("/")[-1].split("\\")[-1]
    if "." not in base:
        return None
    ext = base.rsplit(".", 1)[-1].lower()
    return _EXT_FORMAT.get(ext)


def _sniff_format(audio_bytes: bytes) -> str | None:
    if len(audio_bytes) < 12:
        return None
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "wav"
    if audio_bytes[:3] == b"ID3" or (
        len(audio_bytes) > 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0
    ):
        return "mp3"
    if audio_bytes[:4] == b"fLaC":
        return "flac"
    if audio_bytes[:4] == b"OggS":
        return "ogg"
    if audio_bytes[:4] == b"\x1aE\xdf\xa3":
        return "matroska"
    if audio_bytes[4:8] == b"ftyp":
        return "mp4"
    return None


def _format_candidates(filename: str, audio_bytes: bytes) -> list[str | None]:
    """ffmpeg probe order: auto-detect first, then explicit containers."""
    order: list[str | None] = [None]
    for fmt in (_format_from_filename(filename), _sniff_format(audio_bytes)):
        if fmt and fmt not in order:
            order.append(fmt)
    if "mp4" in order and "mov" not in order:
        order.append("mov")
    return order


def _ffmpeg_decode_to_wav(audio_bytes: bytes, filename: str) -> bytes:
    """Decode any supported container to PCM WAV via ffmpeg (temp file — reliable probe)."""
    candidates = _format_candidates(filename, audio_bytes)
    last_stderr = ""

    for fmt in candidates:
        suffix = _SUFFIX_FOR_FMT.get(fmt, "") if fmt else ".audio"
        if not suffix or suffix == ".audio":
            suffix = ".bin"
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                tmp_path = tmp.name

            cmd = [
                _ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
            ]
            if fmt:
                cmd.extend(["-f", fmt])
            cmd.extend(
                [
                    "-i",
                    tmp_path,
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-f",
                    "wav",
                    "pipe:1",
                ]
            )
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
            last_stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    hint = last_stderr.splitlines()[-1] if last_stderr else "неизвестная ошибка"
    log.warning("audio decode failed for %s (%d bytes): %s", filename, len(audio_bytes), last_stderr)
    raise AudioPrepError(
        "invalid_audio",
        f"Не удалось декодировать аудио: {hint}. "
        "Поддерживаются WAV, MP3, M4A, CAF, OGG, FLAC, WebM.",
    )


def _wav_bytes_to_segment(wav_bytes: bytes) -> AudioSegment:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            nframes = wf.getnframes()
            if channels < 1 or sample_width < 1 or frame_rate < 1 or nframes < 1:
                raise ValueError("empty wav")
            pcm = wf.readframes(nframes)
        return AudioSegment(
            data=pcm,
            sample_width=sample_width,
            frame_rate=frame_rate,
            channels=channels,
        )
    except Exception as e:
        raise AudioPrepError(
            "invalid_audio",
            "Не удалось разобрать WAV после декодирования.",
        ) from e


def _load_segment(audio_bytes: bytes, filename: str = "") -> AudioSegment:
    if not audio_bytes:
        raise AudioPrepError("invalid_audio", "Пустой аудиофайл.")

    if not ffmpeg_available():
        raise AudioPrepError(
            "invalid_audio",
            "ffmpeg недоступен в контейнере backend. Пересоберите образ: docker compose build backend",
        )

    fmt = _format_from_filename(filename) or _sniff_format(audio_bytes)
    if fmt == "wav":
        try:
            return _wav_bytes_to_segment(audio_bytes)
        except AudioPrepError:
            pass

    wav_bytes = _ffmpeg_decode_to_wav(audio_bytes, filename)
    return _wav_bytes_to_segment(wav_bytes)


def _export_wav_bytes(seg: AudioSegment) -> bytes:
    """Export WAV without relying on ffprobe (stdlib wave module)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(seg.channels)
        wf.setsampwidth(seg.sample_width)
        wf.setframerate(seg.frame_rate)
        wf.writeframes(seg.raw_data)
    return buf.getvalue()


def _trim_edges(seg: AudioSegment, threshold_db: float) -> AudioSegment:
    chunks = detect_nonsilent(
        seg,
        min_silence_len=120,
        silence_thresh=threshold_db,
        seek_step=10,
    )
    if not chunks:
        return seg
    start = chunks[0][0]
    end = chunks[-1][1]
    return seg[start:end]


def _apply_playback_speed(seg: AudioSegment, speed: float) -> AudioSegment:
    if abs(speed - 1.0) < 0.001:
        return seg
    speed = _clamp(speed, 0.5, 1.5)
    frame_rate = seg.frame_rate or 44100
    altered = seg._spawn(
        seg.raw_data,
        overrides={"frame_rate": int(frame_rate * speed)},
    )
    return altered.set_frame_rate(frame_rate)


def audio_duration_ms(audio_bytes: bytes, filename: str = "") -> int:
    try:
        seg = _load_segment(audio_bytes, filename)
        return len(seg)
    except AudioPrepError:
        return 0


def prepare_audio(
    audio_bytes: bytes,
    filename: str,
    opts: AudioPrepOptions | None = None,
) -> tuple[bytes, str]:
    """Apply trim, speed, delay, gain, resample; return WAV bytes."""
    options = opts or defaults_from_env()
    seg = _load_segment(audio_bytes, filename)

    if options.trim_silence:
        seg = _trim_edges(seg, options.trim_threshold_db)

    if abs(options.playback_speed - 1.0) > 0.001:
        seg = _apply_playback_speed(seg, options.playback_speed)

    if options.delay_ms > 0:
        seg = AudioSegment.silent(duration=options.delay_ms) + seg

    if abs(options.gain_db) > 0.01:
        seg = seg + options.gain_db

    if options.normalize_peak and seg.max_dBFS != float("-inf"):
        seg = seg.apply_gain(-1.0 - seg.max_dBFS)

    if options.max_duration_sec > 0:
        max_ms = int(options.max_duration_sec * 1000)
        if len(seg) > max_ms:
            seg = seg[:max_ms]

    if options.force_mono and seg.channels > 1:
        seg = seg.set_channels(1)

    if options.sample_rate_hz > 0:
        allowed = {8000, 11025, 16000, 22050, 32000, 44100, 48000}
        rate = options.sample_rate_hz if options.sample_rate_hz in allowed else 16000
        seg = seg.set_frame_rate(rate)

    out_bytes = _export_wav_bytes(seg)
    stem = filename.rsplit(".", 1)[0] if "." in filename else (filename or "audio")
    if "/" in stem or "\\" in stem:
        stem = stem.replace("\\", "/").rsplit("/", 1)[-1]
    return out_bytes, f"{stem}.wav"
