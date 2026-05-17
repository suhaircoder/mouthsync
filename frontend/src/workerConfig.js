const STORAGE_URL = "mouthsync.workerUrl";
const STORAGE_KEY = "mouthsync.workerApiKey";
const STORAGE_WAV2LIP_URL = "mouthsync.wav2lipWorkerUrl";
const STORAGE_WAV2LIP_KEY = "mouthsync.wav2lipWorkerApiKey";
const STORAGE_UPDATED = "mouthsync.workerConfigUpdatedAt";

export function loadWorkerConfig() {
  try {
    return {
      workerUrl: localStorage.getItem(STORAGE_URL) || "",
      workerApiKey: localStorage.getItem(STORAGE_KEY) || "",
      wav2lipWorkerUrl: localStorage.getItem(STORAGE_WAV2LIP_URL) || "",
      wav2lipWorkerApiKey: localStorage.getItem(STORAGE_WAV2LIP_KEY) || "",
      updatedAt: localStorage.getItem(STORAGE_UPDATED) || null,
    };
  } catch {
    return {
      workerUrl: "",
      workerApiKey: "",
      wav2lipWorkerUrl: "",
      wav2lipWorkerApiKey: "",
      updatedAt: null,
    };
  }
}

/** Локально введённые адреса важнее — с сервера подставляем только пустые поля. */
export function mergeWorkerWithRemote(local, remote) {
  if (!remote) return { ...local };
  const pick = (localVal, remoteVal) => {
    const l = (localVal || "").trim();
    if (l) return l;
    return (remoteVal || "").trim();
  };
  return {
    workerUrl: pick(local.workerUrl, remote.workerUrl),
    workerApiKey: pick(local.workerApiKey, remote.workerApiKey),
    wav2lipWorkerUrl: pick(local.wav2lipWorkerUrl, remote.wav2lipWorkerUrl),
    wav2lipWorkerApiKey: pick(local.wav2lipWorkerApiKey, remote.wav2lipWorkerApiKey),
  };
}

export function hasLocalWorkerUrls(config) {
  return Boolean(
    (config.workerUrl || "").trim() || (config.wav2lipWorkerUrl || "").trim(),
  );
}

export function saveWorkerConfig({
  workerUrl,
  workerApiKey,
  wav2lipWorkerUrl,
  wav2lipWorkerApiKey,
}) {
  const url = (workerUrl || "").trim().replace(/\/+$/, "");
  const key = (workerApiKey || "").trim();
  const w2lUrl = (wav2lipWorkerUrl || "").trim().replace(/\/+$/, "");
  const w2lKey = (wav2lipWorkerApiKey || "").trim();

  localStorage.setItem(STORAGE_URL, url);
  localStorage.setItem(STORAGE_KEY, key);
  localStorage.setItem(STORAGE_WAV2LIP_URL, w2lUrl);
  localStorage.setItem(STORAGE_WAV2LIP_KEY, w2lKey);
  const updatedAt = new Date().toISOString();
  localStorage.setItem(STORAGE_UPDATED, updatedAt);

  return {
    workerUrl: url,
    workerApiKey: key,
    wav2lipWorkerUrl: w2lUrl,
    wav2lipWorkerApiKey: w2lKey,
    updatedAt,
  };
}

export function buildWorkerHeaders(
  { workerUrl, workerApiKey, wav2lipWorkerUrl, wav2lipWorkerApiKey },
  extraHeaders = {},
) {
  const headers = { ...extraHeaders };
  const url = (workerUrl || "").trim().replace(/\/+$/, "");
  const key = (workerApiKey || "").trim();
  const w2lUrl = (wav2lipWorkerUrl || "").trim().replace(/\/+$/, "");
  const w2lKey = (wav2lipWorkerApiKey || "").trim();

  if (url) headers["X-Worker-Url"] = url;
  if (key) headers["X-Worker-Key"] = key;
  if (w2lUrl) headers["X-Wav2lip-Worker-Url"] = w2lUrl;
  if (w2lKey) headers["X-Wav2lip-Worker-Key"] = w2lKey;

  return headers;
}

export function workerConfigForApi({
  workerUrl,
  workerApiKey,
  wav2lipWorkerUrl,
  wav2lipWorkerApiKey,
}) {
  return {
    workerUrl: (workerUrl || "").trim().replace(/\/+$/, ""),
    workerApiKey: (workerApiKey || "").trim(),
    wav2lipWorkerUrl: (wav2lipWorkerUrl || "").trim().replace(/\/+$/, ""),
    wav2lipWorkerApiKey: (wav2lipWorkerApiKey || "").trim(),
  };
}

export function hasWorkerConfig({ workerUrl, workerApiKey }, envConfigured) {
  return Boolean((workerUrl || "").trim()) || Boolean(envConfigured);
}

export function hasWav2lipConfig({ wav2lipWorkerUrl }, envWav2lipConfigured) {
  return Boolean((wav2lipWorkerUrl || "").trim()) || Boolean(envWav2lipConfigured);
}
