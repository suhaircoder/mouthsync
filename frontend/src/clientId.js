const STORAGE_CLIENT_ID = "mouthsync.clientId";

function newClientId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `c-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getClientId() {
  try {
    let id = localStorage.getItem(STORAGE_CLIENT_ID);
    if (!id) {
      id = newClientId();
      localStorage.setItem(STORAGE_CLIENT_ID, id);
    }
    return id;
  } catch {
    return newClientId();
  }
}

export function apiHeaders(extra = {}) {
  return {
    "X-Client-Id": getClientId(),
    ...extra,
  };
}
