const STORAGE_URL = "mouthsync.workerUrl";
const STORAGE_KEY = "mouthsync.workerApiKey";

export function loadWorkerConfig() {
  try {
    return {
      workerUrl: localStorage.getItem(STORAGE_URL) || "",
      workerApiKey: localStorage.getItem(STORAGE_KEY) || "",
    };
  } catch {
    return { workerUrl: "", workerApiKey: "" };
  }
}

export function saveWorkerConfig({ workerUrl, workerApiKey }) {
  const url = (workerUrl || "").trim().replace(/\/+$/, "");
  const key = (workerApiKey || "").trim();
  localStorage.setItem(STORAGE_URL, url);
  localStorage.setItem(STORAGE_KEY, key);
  return { workerUrl: url, workerApiKey: key };
}

export function buildWorkerHeaders({ workerUrl, workerApiKey }, extraHeaders = {}) {
  const headers = { ...extraHeaders };
  const url = (workerUrl || "").trim().replace(/\/+$/, "");
  const key = (workerApiKey || "").trim();
  if (url) headers["X-Worker-Url"] = url;
  if (key) headers["X-Worker-Key"] = key;
  return headers;
}

export function workerConfigForApi({ workerUrl, workerApiKey }) {
  return {
    workerUrl: (workerUrl || "").trim().replace(/\/+$/, ""),
    workerApiKey: (workerApiKey || "").trim(),
  };
}

export function hasWorkerConfig({ workerUrl, workerApiKey }, envConfigured) {
  return Boolean((workerUrl || "").trim()) || Boolean(envConfigured);
}
