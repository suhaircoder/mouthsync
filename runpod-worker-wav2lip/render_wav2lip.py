"""Wav2Lip inference wrapper — photo + audio → MP4."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

WAV2LIP_ROOT = Path(os.environ.get("WAV2LIP_ROOT", "/app/Wav2Lip")).resolve()
CHECKPOINT_PATH = Path(
    os.environ.get("WAV2LIP_CHECKPOINT", str(WAV2LIP_ROOT / "checkpoints" / "wav2lip_gan.pth"))
)
WAV2LIP_BATCH_SIZE = os.environ.get("WAV2LIP_BATCH_SIZE", "128")
FACE_DET_BATCH_SIZE = os.environ.get("WAV2LIP_FACE_DET_BATCH_SIZE", "16")
FPS = os.environ.get("WAV2LIP_FPS", "25")


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

    def generate(self, image_path: str, audio_path: str, output_video_path: str) -> None:
        self.verify()
        out = Path(output_video_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "inference.py",
            "--checkpoint_path",
            str(CHECKPOINT_PATH),
            "--face",
            image_path,
            "--audio",
            audio_path,
            "--outfile",
            str(out),
            "--static",
            "True",
            "--fps",
            FPS,
            "--wav2lip_batch_size",
            WAV2LIP_BATCH_SIZE,
            "--face_det_batch_size",
            FACE_DET_BATCH_SIZE,
        ]

        with self._lock:
            proc = subprocess.run(
                cmd,
                cwd=str(WAV2LIP_ROOT),
                capture_output=True,
                text=True,
            )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if "Face not detected" in err:
                raise ValueError(
                    "Face not detected in image. Use a clear front-facing portrait."
                )
            raise RuntimeError(f"Wav2Lip failed: {err[-2000:]}")

        if not out.is_file() or out.stat().st_size < 256:
            raise RuntimeError("Wav2Lip did not produce a valid output video.")


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
