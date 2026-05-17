const STORAGE_KEY = "mouthsync.audioOptions";

export const DEFAULT_AUDIO_OPTIONS = {
  prepEnabled: true,
  delayMs: 0,
  trimSilence: false,
  trimThresholdDb: -40,
  gainDb: 0,
  normalizePeak: false,
  maxDurationSec: 0,
  sampleRateHz: 0,
  forceMono: true,
  playbackSpeed: 1,
};

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

export function normalizeAudioOptions(raw) {
  const base = { ...DEFAULT_AUDIO_OPTIONS, ...raw };
  return {
    prepEnabled: Boolean(base.prepEnabled),
    delayMs: clamp(Math.round(Number(base.delayMs) || 0), 0, 10_000),
    trimSilence: Boolean(base.trimSilence),
    trimThresholdDb: clamp(Number(base.trimThresholdDb) || -40, -60, -20),
    gainDb: clamp(Number(base.gainDb) || 0, -24, 24),
    normalizePeak: Boolean(base.normalizePeak),
    maxDurationSec: clamp(Number(base.maxDurationSec) || 0, 0, 600),
    sampleRateHz: clamp(Math.round(Number(base.sampleRateHz) || 0), 0, 48_000),
    forceMono: Boolean(base.forceMono),
    playbackSpeed: clamp(Number(base.playbackSpeed) || 1, 0.5, 1.5),
  };
}

export function loadAudioOptions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_AUDIO_OPTIONS };
    return normalizeAudioOptions(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_AUDIO_OPTIONS };
  }
}

export function saveAudioOptions(options) {
  const normalized = normalizeAudioOptions(options);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  return normalized;
}

export function audioOptionsFromServer(data) {
  if (!data || typeof data !== "object") return null;
  return normalizeAudioOptions({
    prepEnabled: data.prep_enabled ?? data.enabled,
    delayMs: data.delay_ms,
    trimSilence: data.trim_silence,
    trimThresholdDb: data.trim_threshold_db,
    gainDb: data.gain_db,
    normalizePeak: data.normalize_peak,
    maxDurationSec: data.max_duration_sec,
    sampleRateHz: data.sample_rate_hz,
    forceMono: data.force_mono,
    playbackSpeed: data.playback_speed ?? data.playbackSpeed,
  });
}

export function audioOptionsForApi(options) {
  const o = normalizeAudioOptions(options);
  return {
    prepEnabled: o.prepEnabled,
    delayMs: o.delayMs,
    trimSilence: o.trimSilence,
    trimThresholdDb: o.trimThresholdDb,
    gainDb: o.gainDb,
    normalizePeak: o.normalizePeak,
    maxDurationSec: o.maxDurationSec,
    sampleRateHz: o.sampleRateHz,
    forceMono: o.forceMono,
    playbackSpeed: o.playbackSpeed,
  };
}

export function appendAudioOptionsToFormData(form, options) {
  const o = normalizeAudioOptions(options);
  form.append("audio_prep_enabled", o.prepEnabled ? "1" : "0");
  form.append("audio_delay_ms", String(o.delayMs));
  form.append("audio_trim_silence", o.trimSilence ? "1" : "0");
  form.append("audio_trim_threshold_db", String(o.trimThresholdDb));
  form.append("audio_gain_db", String(o.gainDb));
  form.append("audio_normalize_peak", o.normalizePeak ? "1" : "0");
  form.append("audio_max_duration_sec", String(o.maxDurationSec));
  form.append("audio_sample_rate_hz", String(o.sampleRateHz));
  form.append("audio_force_mono", o.forceMono ? "1" : "0");
  form.append("audio_playback_speed", String(o.playbackSpeed));
}
