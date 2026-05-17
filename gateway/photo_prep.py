"""Portrait validation, enhancement, and normalization before the worker."""

from __future__ import annotations

import io
import os
from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

_cascades: list[cv2.CascadeClassifier] | None = None

# Haar minSize only — separate from user «min face share» validation
_DETECT_MIN_SIZE_RATIO = 0.06


class FaceCheckError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class PhotoPrepOptions:
    face_check_enabled: bool = True
    face_require_single: bool = True
    face_auto_crop: bool = True
    max_edge_px: int = 2048
    min_face_size_ratio: float = 0.08
    brightness: float = 1.0
    contrast: float = 1.0
    sharpness: float = 1.0
    jpeg_quality: int = 92


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def defaults_from_env() -> PhotoPrepOptions:
    return PhotoPrepOptions(
        face_check_enabled=_env_flag("FACE_CHECK_ENABLED"),
        face_require_single=_env_flag("FACE_REQUIRE_SINGLE"),
        face_auto_crop=_env_flag("FACE_AUTO_CROP", "1"),
        max_edge_px=_env_int("PHOTO_MAX_EDGE", 2048),
        min_face_size_ratio=_env_float("FACE_MIN_SIZE_RATIO", 0.08),
        brightness=_env_float("PHOTO_BRIGHTNESS", 1.0),
        contrast=_env_float("PHOTO_CONTRAST", 1.0),
        sharpness=_env_float("PHOTO_SHARPNESS", 1.0),
        jpeg_quality=_env_int("PHOTO_JPEG_QUALITY", 92),
    )


def photo_prep_defaults() -> dict[str, Any]:
    data = asdict(defaults_from_env())
    data["backend"] = "opencv_haar"
    return data


def _parse_bool(raw: str | None, fallback: bool) -> bool:
    if raw is None or raw == "":
        return fallback
    return raw.strip().lower() in ("1", "true", "yes", "on")


def options_from_form(
    *,
    face_check_enabled: str | None = None,
    face_require_single: str | None = None,
    face_auto_crop: str | None = None,
    photo_max_edge: str | None = None,
    face_min_size_ratio: str | None = None,
    photo_brightness: str | None = None,
    photo_contrast: str | None = None,
    photo_sharpness: str | None = None,
    photo_jpeg_quality: str | None = None,
) -> PhotoPrepOptions:
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

    return PhotoPrepOptions(
        face_check_enabled=_parse_bool(face_check_enabled, base.face_check_enabled),
        face_require_single=_parse_bool(face_require_single, base.face_require_single),
        face_auto_crop=_parse_bool(face_auto_crop, base.face_auto_crop),
        max_edge_px=_int(photo_max_edge, base.max_edge_px, 512, 4096),
        min_face_size_ratio=_float(face_min_size_ratio, base.min_face_size_ratio, 0.03, 0.5),
        brightness=_float(photo_brightness, base.brightness, 0.5, 2.0),
        contrast=_float(photo_contrast, base.contrast, 0.5, 2.0),
        sharpness=_float(photo_sharpness, base.sharpness, 0.5, 2.5),
        jpeg_quality=_int(photo_jpeg_quality, base.jpeg_quality, 60, 100),
    )


def _get_cascades() -> list[cv2.CascadeClassifier]:
    global _cascades
    if _cascades is None:
        names = (
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
        )
        loaded: list[cv2.CascadeClassifier] = []
        for name in names:
            path = cv2.data.haarcascades + name
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                loaded.append(cascade)
        if not loaded:
            raise RuntimeError("Failed to load OpenCV face cascades")
        _cascades = loaded
    return _cascades


def _load_rgb(photo_bytes: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(photo_bytes))
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except UnidentifiedImageError as e:
        raise FaceCheckError(
            "invalid_image",
            "Не удалось прочитать изображение. Используйте JPG, PNG или WebP.",
        ) from e


def _resize_if_needed(img: Image.Image, max_edge_px: int) -> Image.Image:
    w, h = img.size
    max_edge = max(w, h)
    if max_edge <= max_edge_px:
        return img
    scale = max_edge_px / max_edge
    return img.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))),
        Image.Resampling.LANCZOS,
    )


def _apply_enhancements(img: Image.Image, opts: PhotoPrepOptions) -> Image.Image:
    if abs(opts.brightness - 1.0) > 0.01:
        img = ImageEnhance.Brightness(img).enhance(opts.brightness)
    if abs(opts.contrast - 1.0) > 0.01:
        img = ImageEnhance.Contrast(img).enhance(opts.contrast)
    if abs(opts.sharpness - 1.0) > 0.01:
        img = ImageEnhance.Sharpness(img).enhance(opts.sharpness)
    return img


def _box_area(box: tuple[int, int, int, int]) -> int:
    return box[2] * box[3]


def _box_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _cluster_face_boxes(
    boxes: list[tuple[int, int, int, int]],
    *,
    iou_threshold: float = 0.35,
) -> list[tuple[int, int, int, int]]:
    """Merge overlapping detections (same face often counted twice by Haar)."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=_box_area, reverse=True)
    clusters: list[tuple[int, int, int, int]] = []
    for box in ordered:
        merged = False
        for i, kept in enumerate(clusters):
            if _box_iou(box, kept) >= iou_threshold:
                if _box_area(box) > _box_area(kept):
                    clusters[i] = box
                merged = True
                break
        if not merged:
            clusters.append(box)
    return clusters


def _significant_face_boxes(
    boxes: list[tuple[int, int, int, int]],
    *,
    min_relative_area: float = 0.22,
) -> list[tuple[int, int, int, int]]:
    """Drop tiny false positives far smaller than the main face."""
    if not boxes:
        return []
    max_area = max(_box_area(b) for b in boxes)
    threshold = max_area * min_relative_area
    return [b for b in boxes if _box_area(b) >= threshold]


def _detect_face_boxes_raw(rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    short_edge = min(gray.shape[:2])
    min_size = max(24, int(short_edge * _DETECT_MIN_SIZE_RATIO))
    merged: list[tuple[int, int, int, int]] = []
    for cascade in _get_cascades():
        raw = cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(min_size, min_size),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        for box in raw:
            merged.append(tuple(int(v) for v in box))
    return _significant_face_boxes(_cluster_face_boxes(merged))


def _face_area_ratio(box: tuple[int, int, int, int], img_w: int, img_h: int) -> float:
    if img_w <= 0 or img_h <= 0:
        return 0.0
    return _box_area(box) / float(img_w * img_h)


def _expand_face_crop_rect(
    box: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int]:
    """Crop region with extra space below the Haar box for mouth and chin (lip-sync)."""
    x, y, w, h = box
    pad_sides = int(w * 0.55)
    pad_top = int(h * 0.55)
    pad_bottom = int(h * 0.85)
    x1 = max(0, x - pad_sides)
    y1 = max(0, y - pad_top)
    x2 = min(img_w, x + w + pad_sides)
    y2 = min(img_h, y + h + pad_bottom)
    cw, ch = x2 - x1, y2 - y1
    side = max(cw, ch)
    cx = (x1 + x2) // 2
    cy = y1 + int(ch * 0.42)
    x1 = max(0, cx - side // 2)
    y1 = max(0, cy - side // 2)
    x2 = min(img_w, x1 + side)
    y2 = min(img_h, y1 + side)
    if x2 - x1 < w or y2 - y1 < h:
        x1, y1 = max(0, x - pad_sides), max(0, y - pad_top)
        x2, y2 = min(img_w, x + w + pad_sides), min(img_h, y + h + pad_bottom)
    return x1, y1, x2 - x1, y2 - y1


def _crop_image_to_face(img: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    w, h = img.size
    x, y, cw, ch = _expand_face_crop_rect(box, w, h)
    return img.crop((x, y, x + cw, y + ch))


def _validate_and_crop_face(img: Image.Image, options: PhotoPrepOptions) -> Image.Image:
    rgb = np.asarray(img)
    h, w = rgb.shape[:2]
    boxes = _detect_face_boxes_raw(rgb)
    if not boxes:
        raise FaceCheckError(
            "no_face",
            "Лицо не найдено. Используйте чёткий портрет анфас: лицо и рот видны, без сильного поворота.",
        )

    main = max(boxes, key=_box_area)
    share = _face_area_ratio(main, w, h)
    if share < options.min_face_size_ratio:
        pct = int(share * 100)
        need = int(options.min_face_size_ratio * 100)
        raise FaceCheckError(
            "face_too_small",
            f"Лицо занимает {pct}% кадра, нужно минимум {need}%. "
            "Подойдите ближе к камере или уменьшите «мин. доля лица» в настройках.",
        )

    if options.face_require_single and len(boxes) > 1:
        raise FaceCheckError(
            "multiple_faces",
            f"Найдено несколько лиц ({len(boxes)}). Используйте фото с одним человеком.",
        )

    if options.face_auto_crop:
        return _crop_image_to_face(img, main)
    return img


def prepare_photo_baseline(
    photo_bytes: bytes,
    filename: str,
    opts: PhotoPrepOptions | None = None,
) -> tuple[bytes, str]:
    """EXIF fix + resize only — preview «до» настроек улучшения."""
    options = opts or defaults_from_env()
    img = _resize_if_needed(_load_rgb(photo_bytes), options.max_edge_px)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return out.getvalue(), f"{stem}.jpg"


def prepare_photo(
    photo_bytes: bytes,
    filename: str,
    opts: PhotoPrepOptions | None = None,
) -> tuple[bytes, str]:
    """Normalize, enhance, validate face(s), return JPEG bytes."""
    options = opts or defaults_from_env()
    img = _resize_if_needed(_load_rgb(photo_bytes), options.max_edge_px)
    img = _apply_enhancements(img, options)

    if options.face_check_enabled:
        img = _validate_and_crop_face(img, options)

    out = io.BytesIO()
    img.save(
        out,
        format="JPEG",
        quality=options.jpeg_quality,
        optimize=True,
    )
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return out.getvalue(), f"{stem}.jpg"
