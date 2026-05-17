import os
import shlex
import tempfile

import cv2
import librosa
import mediapipe as mp
import numpy as np

FPS = 30
LOWER_LIP_LANDMARK_INDEX = 14
MAX_LIP_SHIFT_PX = 18


def _compute_rms_per_frame(audio_path: str, fps: int) -> tuple[np.ndarray, int, int]:
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    hop_length = max(1, int(sr / fps))
    frame_length = max(hop_length * 2, 512)
    rms = librosa.feature.rms(
        y=y, frame_length=frame_length, hop_length=hop_length, center=True
    )[0]
    n_frames = int(np.ceil(len(y) / sr * fps))
    if len(rms) < n_frames:
        rms = np.pad(rms, (0, n_frames - len(rms)), mode="edge")
    else:
        rms = rms[:n_frames]
    rmin, rmax = float(np.min(rms)), float(np.max(rms))
    if rmax - rmin < 1e-9:
        rms_norm = np.zeros_like(rms)
    else:
        rms_norm = (rms - rmin) / (rmax - rmin)
    return rms_norm.astype(np.float32), n_frames, sr


def _mouth_bbox_from_landmarks(
    landmarks, w: int, h: int, padding_ratio: float = 0.35
) -> tuple[int, int, int, int]:
    mp_face_mesh = mp.solutions.face_mesh
    xs, ys = [], []
    for a, b in mp_face_mesh.FACEMESH_LIPS:
        for idx in (a, b):
            lm = landmarks.landmark[idx]
            xs.append(lm.x * w)
            ys.append(lm.y * h)
    x0, x1 = int(min(xs)), int(max(xs))
    y0, y1 = int(min(ys)), int(max(ys))
    pw = int((x1 - x0) * padding_ratio)
    ph = int((y1 - y0) * padding_ratio)
    x0 = max(0, x0 - pw)
    y0 = max(0, y0 - ph)
    x1 = min(w - 1, x1 + pw)
    y1 = min(h - 1, y1 + ph)
    return x0, y0, x1, y1


def animate_face(image_path: str, audio_path: str, output_video_path: str) -> None:
    rms_norm, n_frames, _sr = _compute_rms_per_frame(audio_path, FPS)

    bgr = cv2.imread(image_path)
    if bgr is None:
        raise ValueError(f"Cannot read image: {image_path}")

    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    mp_face_mesh = mp.solutions.face_mesh
    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(rgb)
        if not results.multi_face_landmarks:
            raise ValueError("Face not found (MediaPipe Face Mesh).")

        landmarks = results.multi_face_landmarks[0]
        mx0, my0, mx1, my1 = _mouth_bbox_from_landmarks(landmarks, w, h)

        lip_anchor = landmarks.landmark[LOWER_LIP_LANDMARK_INDEX]
        lip_y_px = int(lip_anchor.y * h)
        my1 = min(h - 1, max(my1, lip_y_px + max(4, int(0.02 * h))))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fd, silent_path = tempfile.mkstemp(suffix="_silent.mp4")
    os.close(fd)
    writer = cv2.VideoWriter(silent_path, fourcc, FPS, (w, h))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter init failed.")

    try:
        for i in range(n_frames):
            frame = bgr.copy()
            shift = float(rms_norm[i]) * MAX_LIP_SHIFT_PX

            mouth_roi = frame[my0 : my1 + 1, mx0 : mx1 + 1].copy()
            if mouth_roi.size == 0:
                writer.write(frame)
                continue

            mh, mw = mouth_roi.shape[:2]
            M = np.float32([[1.0, 0.0, 0.0], [0.0, 1.0, shift]])
            warped = cv2.warpAffine(
                mouth_roi,
                M,
                (mw, mh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            frame[my0 : my1 + 1, mx0 : mx1 + 1] = warped

            writer.write(frame)
    finally:
        writer.release()

    cmd = (
        "ffmpeg -y -i "
        + shlex.quote(silent_path)
        + " -i "
        + shlex.quote(audio_path)
        + " -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "
        + shlex.quote(output_video_path)
    )
    rc = os.system(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with status {rc}")

    try:
        os.remove(silent_path)
    except OSError:
        pass
