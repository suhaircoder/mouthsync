"""Wav2Lip inference wrapper — photo + audio → MP4."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

WAV2LIP_ROOT = Path(os.environ.get("WAV2LIP_ROOT", "/app/Wav2Lip")).resolve()
CHECKPOINT_PATH = Path(
    os.environ.get("WAV2LIP_CHECKPOINT", str(WAV2LIP_ROOT / "checkpoints" / "wav2lip_gan.pth"))
)
WAV2LIP_BATCH_SIZE = os.environ.get("WAV2LIP_BATCH_SIZE", "128")
FACE_DET_BATCH_SIZE = os.environ.get("WAV2LIP_FACE_DET_BATCH_SIZE", "16")
FPS = os.environ.get("WAV2LIP_FPS", "25")
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def _ffmpeg_bin() -> str:
    """Prefer system ffmpeg (libx264); conda ffmpeg in PyTorch images often lacks it."""
    for candidate in ("/usr/bin/ffmpeg", shutil.which("ffmpeg")):
        if candidate and Path(candidate).is_file():
            return candidate
    return "ffmpeg"


def _ffprobe_bin() -> str:
    for candidate in ("/usr/bin/ffprobe", shutil.which("ffprobe")):
        if candidate and Path(candidate).is_file():
            return candidate
    return "ffprobe"


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXTS


def _parse_fps(value: str) -> float:
    value = value.strip()
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        num, den = value.split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(value)


def _probe_video_fps(video_path: str) -> float:
    """SadTalker MP4s often report fps=0 to OpenCV; ffprobe is more reliable."""
    for field in ("avg_frame_rate", "r_frame_rate"):
        try:
            raw = subprocess.check_output(
                [
                    _ffprobe_bin(),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    f"stream={field}",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                text=True,
            ).strip()
            fps = _parse_fps(raw)
            if fps > 1:
                return fps
        except (subprocess.CalledProcessError, ValueError, OSError):
            continue
    try:
        return float(FPS)
    except ValueError:
        return 25.0


def _normalize_audio_for_wav2lip(audio_path: str) -> tuple[str, Path | None]:
    """Convert any audio to 16 kHz mono PCM WAV (Wav2Lip expects 16 kHz)."""
    src = Path(audio_path)
    fd, tmp_name = tempfile.mkstemp(suffix=".wav", prefix="w2l_audio_")
    os.close(fd)
    tmp = Path(tmp_name)
    proc = subprocess.run(
        [
            _ffmpeg_bin(),
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(tmp),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        err = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise ValueError(f"Could not prepare audio: {err[-500:]}")
    return str(tmp), tmp


def _transcode_for_browser(mp4_path: Path) -> None:
    """Wav2Lip muxes DIVX into MP4 — many browsers play audio only. Re-encode for HTML5."""
    ffmpeg = _ffmpeg_bin()
    fd, tmp_name = tempfile.mkstemp(suffix=".mp4", prefix="w2l_web_")
    os.close(fd)
    tmp = Path(tmp_name)

    base = [
        ffmpeg,
        "-y",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(mp4_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-movflags",
        "+faststart",
    ]
    # libx264 (no -preset: not supported by minimal conda ffmpeg builds)
    attempts: list[list[str]] = [
        [
            *base,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(tmp),
        ],
        [
            *base,
            "-c:v",
            "mpeg4",
            "-vtag",
            "mp4v",
            "-pix_fmt",
            "yuv420p",
            "-q:v",
            "4",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(tmp),
        ],
    ]

    last_err = ""
    for cmd in attempts:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 256:
            tmp.replace(mp4_path)
            return
        last_err = (proc.stderr or proc.stdout or "ffmpeg transcode failed").strip()
        tmp.unlink(missing_ok=True)
        fd, tmp_name = tempfile.mkstemp(suffix=".mp4", prefix="w2l_web_")
        os.close(fd)
        tmp = Path(tmp_name)

    tmp.unlink(missing_ok=True)
    raise RuntimeError(f"Could not prepare browser-compatible video: {last_err[-500:]}")


def _friendly_wav2lip_error(err: str) -> str:
    if "_build_mel_basis" in err or "melspectrogram" in err:
        return (
            "Audio mel-spectrogram failed (librosa). Rebuild the Wav2Lip worker image "
            "with the latest Dockerfile patches."
        )
    if "Face not detected" in err:
        return (
            "Face not detected. Use a clear front-facing portrait or video with a visible face."
        )
    return f"Wav2Lip failed: {err[-1500:]}"


class Wav2LipEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._verified = False

    def verify(self) -> None:
        if self._verified:
            return
        with self._lock:
            if self._verified:
                return
            if not WAV2LIP_ROOT.is_dir():
                raise RuntimeError(f"Wav2Lip not found at {WAV2LIP_ROOT}")
            if not CHECKPOINT_PATH.is_file():
                raise RuntimeError(f"Checkpoint missing: {CHECKPOINT_PATH}")
            (WAV2LIP_ROOT / "temp").mkdir(parents=True, exist_ok=True)
            self._verified = True

    def _run_inference(
        self,
        face_path: str,
        audio_path: str,
        output_video_path: str,
        *,
        static: bool,
    ) -> None:
        self.verify()
        out = Path(output_video_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        prepared_audio, audio_tmp = _normalize_audio_for_wav2lip(audio_path)
        try:
            self._run_inference_subprocess(
                face_path, prepared_audio, out, static=static
            )
        finally:
            if audio_tmp is not None:
                audio_tmp.unlink(missing_ok=True)

    def _run_inference_subprocess(
        self,
        face_path: str,
        audio_path: str,
        out: Path,
        *,
        static: bool,
    ) -> None:
        # Wav2Lip uses argparse type=bool: bool("False") is True — never pass "--static False".
        fps = FPS
        if not _is_image(face_path):
            fps = str(_probe_video_fps(face_path))

        cmd = [
            sys.executable,
            "inference.py",
            "--checkpoint_path",
            str(CHECKPOINT_PATH),
            "--face",
            face_path,
            "--audio",
            audio_path,
            "--outfile",
            str(out),
            "--fps",
            fps,
            "--wav2lip_batch_size",
            WAV2LIP_BATCH_SIZE,
            "--face_det_batch_size",
            FACE_DET_BATCH_SIZE,
        ]
        if static:
            cmd.extend(["--static", "True"])

        with self._lock:
            proc = subprocess.run(
                cmd,
                cwd=str(WAV2LIP_ROOT),
                capture_output=True,
                text=True,
            )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            msg = _friendly_wav2lip_error(err)
            if "Face not detected" in err:
                raise ValueError(msg)
            raise RuntimeError(msg)

        if not out.is_file() or out.stat().st_size < 256:
            raise RuntimeError("Wav2Lip did not produce a valid output video.")

        _transcode_for_browser(out)

    def generate(self, image_path: str, audio_path: str, output_video_path: str) -> None:
        self._run_inference(image_path, audio_path, output_video_path, static=True)

    def refine_video(self, video_path: str, audio_path: str, output_video_path: str) -> None:
        """Re-sync lips in an existing video (post-process after SadTalker etc.)."""
        self._run_inference(video_path, audio_path, output_video_path, static=False)


_engine: Wav2LipEngine | None = None


def get_engine() -> Wav2LipEngine:
    global _engine
    if _engine is None:
        _engine = Wav2LipEngine()
    return _engine


def preload_models() -> None:
    get_engine().verify()


def animate_face(image_path: str, audio_path: str, output_video_path: str) -> None:
    get_engine().generate(image_path, audio_path, output_video_path)


def refine_video(video_path: str, audio_path: str, output_video_path: str) -> None:
    get_engine().refine_video(video_path, audio_path, output_video_path)


def backend_info() -> dict:
    ckpt_ok = CHECKPOINT_PATH.is_file()
    root_ok = WAV2LIP_ROOT.is_dir()
    ready = ckpt_ok and root_ok
    return {
        "backend": "wav2lip",
        "ready": ready,
        "checkpoint": str(CHECKPOINT_PATH),
        "wav2lip_root": str(WAV2LIP_ROOT),
    }
