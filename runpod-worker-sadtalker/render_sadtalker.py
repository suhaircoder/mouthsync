"""SadTalker inference wrapper — same entrypoint as lightweight runpod-worker."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import tempfile
from pathlib import Path
import torch

SADTALKER_ROOT = Path(os.environ.get("SADTALKER_ROOT", "/app/SadTalker")).resolve()
if str(SADTALKER_ROOT) not in sys.path:
    sys.path.insert(0, str(SADTALKER_ROOT))

CHECKPOINT_DIR = os.environ.get("SADTALKER_CHECKPOINT_DIR", str(SADTALKER_ROOT / "checkpoints"))
CONFIG_DIR = str(SADTALKER_ROOT / "src" / "config")
SIZE = int(os.environ.get("SADTALKER_SIZE", "256"))
PREPROCESS = os.environ.get("SADTALKER_PREPROCESS", "crop")
STILL = os.environ.get("SADTALKER_STILL", "1").strip().lower() in ("1", "true", "yes")
BATCH_SIZE = int(os.environ.get("SADTALKER_BATCH_SIZE", "2"))
POSE_STYLE = int(os.environ.get("SADTALKER_POSE_STYLE", "0"))
EXPRESSION_SCALE = float(os.environ.get("SADTALKER_EXPRESSION_SCALE", "1.0"))
ENHANCER = os.environ.get("SADTALKER_ENHANCER", "").strip() or None
BACKGROUND_ENHANCER = os.environ.get("SADTALKER_BACKGROUND_ENHANCER", "").strip() or None


class SadTalkerEngine:
    """Load SadTalker models once; run inference under a GPU lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self.device: str = "cpu"
        self.preprocess_model = None
        self.audio_to_coeff = None
        self.animate_from_coeff = None
        self.sadtalker_paths: dict | None = None

    def load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"

            from src.facerender.animate import AnimateFromCoeff
            from src.test_audio2coeff import Audio2Coeff
            from src.utils.init_path import init_path
            from src.utils.preprocess import CropAndExtract

            self.sadtalker_paths = init_path(
                CHECKPOINT_DIR,
                CONFIG_DIR,
                SIZE,
                old_version=False,
                preprocess=PREPROCESS,
            )
            self.preprocess_model = CropAndExtract(self.sadtalker_paths, self.device)
            self.audio_to_coeff = Audio2Coeff(self.sadtalker_paths, self.device)
            self.animate_from_coeff = AnimateFromCoeff(self.sadtalker_paths, self.device)
            self._loaded = True

    def generate(self, image_path: str, audio_path: str, output_video_path: str) -> None:
        self.load()
        assert self.preprocess_model is not None
        assert self.audio_to_coeff is not None
        assert self.animate_from_coeff is not None

        from src.generate_batch import get_data
        from src.generate_facerender_batch import get_facerender_data

        save_dir = tempfile.mkdtemp(prefix="sadtalker_")
        try:
            with self._lock:
                first_frame_dir = os.path.join(save_dir, "first_frame_dir")
                os.makedirs(first_frame_dir, exist_ok=True)

                first_coeff_path, crop_pic_path, crop_info = self.preprocess_model.generate(
                    image_path,
                    first_frame_dir,
                    PREPROCESS,
                    source_image_flag=True,
                    pic_size=SIZE,
                )
                if first_coeff_path is None:
                    raise ValueError(
                        "Face not detected in image (SadTalker preprocess). "
                        "Use a clear front-facing portrait."
                    )

                batch = get_data(
                    first_coeff_path,
                    audio_path,
                    self.device,
                    ref_eyeblink_coeff_path=None,
                    still=STILL,
                )
                coeff_path = self.audio_to_coeff.generate(
                    batch, save_dir, POSE_STYLE, ref_pose_coeff_path=None
                )

                data = get_facerender_data(
                    coeff_path,
                    crop_pic_path,
                    first_coeff_path,
                    audio_path,
                    BATCH_SIZE,
                    None,
                    None,
                    None,
                    expression_scale=EXPRESSION_SCALE,
                    still_mode=STILL,
                    preprocess=PREPROCESS,
                    size=SIZE,
                )

                result = self.animate_from_coeff.generate(
                    data,
                    save_dir,
                    image_path,
                    crop_info,
                    enhancer=ENHANCER,
                    background_enhancer=BACKGROUND_ENHANCER,
                    preprocess=PREPROCESS,
                    img_size=SIZE,
                )

                generated = save_dir + ".mp4"
                if result and os.path.isfile(result):
                    shutil.move(result, generated)
                elif not os.path.isfile(generated):
                    # inference.py moves result to save_dir+.mp4
                    raise RuntimeError("SadTalker did not produce an output video.")

                shutil.copy2(generated, output_video_path)
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)


_engine: SadTalkerEngine | None = None


def get_engine() -> SadTalkerEngine:
    global _engine
    if _engine is None:
        _engine = SadTalkerEngine()
    return _engine


def animate_face(image_path: str, audio_path: str, output_video_path: str) -> None:
    """MouthSync worker API — photo + audio → MP4 via SadTalker."""
    get_engine().generate(image_path, audio_path, output_video_path)


def backend_info() -> dict[str, str | bool | int]:
    eng = get_engine()
    loaded = eng._loaded
    return {
        "backend": "sadtalker",
        "ready": loaded,
        "device": eng.device if loaded else ("cuda" if torch.cuda.is_available() else "cpu"),
        "models_loaded": loaded,
        "size": SIZE,
        "preprocess": PREPROCESS,
        "still": STILL,
    }
