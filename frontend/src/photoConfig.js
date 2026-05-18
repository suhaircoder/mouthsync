const STORAGE_KEY = "mouthsync.photoOptions";

export const DEFAULT_PHOTO_OPTIONS = {
  prepEnabled: true,
  faceCheckEnabled: true,
  faceRequireSingle: true,
  faceAutoCrop: true,
  faceAlignEnabled: false,
  maxEdge: 2048,
  minFaceSizeRatio: 0.08,
  brightness: 1,
  contrast: 1,
  sharpness: 1,
  jpegQuality: 92,
};

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

export function normalizePhotoOptions(raw) {
  const base = { ...DEFAULT_PHOTO_OPTIONS, ...raw };
  return {
    prepEnabled: Boolean(base.prepEnabled),
    faceCheckEnabled: Boolean(base.faceCheckEnabled),
    faceRequireSingle: Boolean(base.faceRequireSingle),
    faceAutoCrop: Boolean(base.faceAutoCrop),
    faceAlignEnabled: Boolean(base.faceAlignEnabled),
    maxEdge: clamp(Number(base.maxEdge) || 2048, 512, 4096),
    minFaceSizeRatio: clamp(Number(base.minFaceSizeRatio) || 0.08, 0.03, 0.5),
    brightness: clamp(Number(base.brightness) || 1, 0.5, 2),
    contrast: clamp(Number(base.contrast) || 1, 0.5, 2),
    sharpness: clamp(Number(base.sharpness) || 1, 0.5, 2.5),
    jpegQuality: clamp(Math.round(Number(base.jpegQuality) || 92), 60, 100),
  };
}

export function loadPhotoOptions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PHOTO_OPTIONS };
    return normalizePhotoOptions(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_PHOTO_OPTIONS };
  }
}

export function savePhotoOptions(options) {
  const normalized = normalizePhotoOptions(options);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  return normalized;
}

/** Merge server defaults (snake_case) into UI shape when /health or /api/photo-defaults loads. */
export function photoOptionsFromServer(data) {
  if (!data || typeof data !== "object") return null;
  return normalizePhotoOptions({
    prepEnabled: data.prep_enabled ?? data.enabled,
    faceCheckEnabled: data.face_check_enabled,
    faceRequireSingle: data.face_require_single,
    faceAutoCrop: data.face_auto_crop,
    faceAlignEnabled: data.face_align_enabled,
    maxEdge: data.max_edge_px,
    minFaceSizeRatio: data.min_face_size_ratio,
    brightness: data.brightness,
    contrast: data.contrast,
    sharpness: data.sharpness,
    jpegQuality: data.jpeg_quality,
  });
}

export function photoOptionsForApi(options) {
  const o = normalizePhotoOptions(options);
  return {
    prepEnabled: o.prepEnabled,
    faceCheckEnabled: o.faceCheckEnabled,
    faceRequireSingle: o.faceRequireSingle,
    faceAutoCrop: o.faceAutoCrop,
    faceAlignEnabled: o.faceAlignEnabled,
    maxEdge: o.maxEdge,
    minFaceSizeRatio: o.minFaceSizeRatio,
    brightness: o.brightness,
    contrast: o.contrast,
    sharpness: o.sharpness,
    jpegQuality: o.jpegQuality,
  };
}

export function appendPhotoOptionsToFormData(form, options) {
  const o = normalizePhotoOptions(options);
  form.append("photo_prep_enabled", o.prepEnabled ? "1" : "0");
  form.append("face_check_enabled", o.faceCheckEnabled ? "1" : "0");
  form.append("face_require_single", o.faceRequireSingle ? "1" : "0");
  form.append("face_auto_crop", o.faceAutoCrop ? "1" : "0");
  form.append("face_align_enabled", o.faceAlignEnabled ? "1" : "0");
  form.append("photo_max_edge", String(o.maxEdge));
  form.append("face_min_size_ratio", String(o.minFaceSizeRatio));
  form.append("photo_brightness", String(o.brightness));
  form.append("photo_contrast", String(o.contrast));
  form.append("photo_sharpness", String(o.sharpness));
  form.append("photo_jpeg_quality", String(o.jpegQuality));
}
