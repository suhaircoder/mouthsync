import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import {
  buildWorkerHeaders,
  hasWorkerConfig,
  loadWorkerConfig,
  saveWorkerConfig,
} from "./workerConfig.js";

const API_GENERATE = "/api/generate";
const API_WORKER_STATUS = "/api/worker-status";
const API_HISTORY = "/api/history";

function formatHistoryDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-US", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function FileDropZone({ id, label, hint, accept, disabled, file, onChange }) {
  const inputRef = useRef(null);

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div
      className={`dropzone ${file ? "dropzone--filled" : ""} ${disabled ? "dropzone--disabled" : ""}`}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        className="dropzone__input"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <button
        type="button"
        className="dropzone__surface"
        onClick={openPicker}
        disabled={disabled}
        aria-labelledby={`${id}-label`}
      >
        <span className="dropzone__icon" aria-hidden>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </span>
        <span className="dropzone__text">
          <span id={`${id}-label`} className="dropzone__label">
            {label}
          </span>
          <span className="dropzone__hint">{hint}</span>
          {file ? (
            <span className="dropzone__filename">{file.name}</span>
          ) : null}
        </span>
      </button>
    </div>
  );
}

export default function App() {
  const [photo, setPhoto] = useState(null);
  const [audio, setAudio] = useState(null);
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [workerUrl, setWorkerUrl] = useState("");
  const [workerApiKey, setWorkerApiKey] = useState("");
  const [envWorkerConfigured, setEnvWorkerConfigured] = useState(false);
  const [testingWorker, setTestingWorker] = useState(false);
  const [status, setStatus] = useState({
    tone: "neutral",
    text: "Enter your RunPod worker URL in settings below (or set WORKER_URL in .env).",
  });
  const [videoUrl, setVideoUrl] = useState(null);
  const [historyItems, setHistoryItems] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const prevUrlRef = useRef(null);

  const workerConfig = { workerUrl, workerApiKey };
  const workerHeaders = () => buildWorkerHeaders(workerConfig);

  const revokePrev = useCallback(() => {
    if (prevUrlRef.current?.startsWith("blob:")) {
      URL.revokeObjectURL(prevUrlRef.current);
    }
    prevUrlRef.current = null;
  }, []);

  useEffect(() => () => revokePrev(), [revokePrev]);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(API_HISTORY);
      if (!res.ok) return;
      const data = await res.json();
      setHistoryItems(data.items || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const saved = loadWorkerConfig();
    setWorkerUrl(saved.workerUrl);
    setWorkerApiKey(saved.workerApiKey);

    fetch("/health")
      .then((r) => r.json())
      .then((data) => {
        const envOk = Boolean(data.worker_configured);
        setEnvWorkerConfigured(envOk);
        if (saved.workerUrl || envOk) {
          setStatus({
            tone: "neutral",
            text: saved.workerUrl
              ? "Worker URL loaded from browser settings."
              : "Using WORKER_URL from gateway .env.",
          });
        }
      })
      .catch(() => {});
    loadHistory();
  }, [loadHistory]);

  const playHistoryItem = (item) => {
    revokePrev();
    setActiveHistoryId(item.id);
    setVideoUrl(item.video_url);
    setStatus({
      tone: "neutral",
      text: `From history: ${item.photo_name} + ${item.audio_name}`,
    });
  };

  const onDeleteHistory = async (id) => {
    try {
      const res = await fetch(`${API_HISTORY}/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (activeHistoryId === id) {
        revokePrev();
        setVideoUrl(null);
        setActiveHistoryId(null);
      }
      await loadHistory();
      setStatus({ tone: "ok", text: "Entry removed from history." });
    } catch (err) {
      setStatus({
        tone: "err",
        text: err?.message || String(err),
      });
    }
  };

  const onSaveWorkerSettings = (e) => {
    e.preventDefault();
    const saved = saveWorkerConfig({ workerUrl, workerApiKey });
    setWorkerUrl(saved.workerUrl);
    setWorkerApiKey(saved.workerApiKey);
    setStatus({
      tone: "ok",
      text: "Worker settings saved in this browser.",
    });
  };

  const onTestWorker = async () => {
    setTestingWorker(true);
    try {
      const res = await fetch(API_WORKER_STATUS, { headers: workerHeaders() });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        setStatus({
          tone: "ok",
          text: `Worker reachable: ${data.worker_url}`,
        });
      } else {
        setStatus({
          tone: "err",
          text: data.detail || `Check failed (${res.status})`,
        });
      }
    } catch (err) {
      setStatus({
        tone: "err",
        text: err?.message || String(err),
      });
    } finally {
      setTestingWorker(false);
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!photo || !audio) {
      setStatus({
        tone: "warn",
        text: "Both files are required: face image and audio.",
      });
      return;
    }

    if (!hasWorkerConfig(workerConfig, envWorkerConfigured)) {
      setStatus({
        tone: "warn",
        text: "Set worker URL in settings or in .env first.",
      });
      setSettingsOpen(true);
      return;
    }

    setLoading(true);
    setStatus({
      tone: "neutral",
      text: "Sending to worker… this may take a minute or longer.",
    });

    const form = new FormData();
    form.append("photo", photo);
    form.append("audio", audio);

    try {
      const res = await fetch(API_GENERATE, {
        method: "POST",
        headers: workerHeaders(),
        body: form,
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(t || `Error ${res.status}`);
      }
      const historyId = res.headers.get("X-History-Id");
      const blob = await res.blob();
      revokePrev();
      const url = URL.createObjectURL(blob);
      prevUrlRef.current = url;
      setVideoUrl(url);
      setActiveHistoryId(historyId);
      await loadHistory();
      setStatus({
        tone: "ok",
        text: historyId
          ? "Done. Video saved to gateway history."
          : "Done. Preview below plays automatically.",
      });
    } catch (err) {
      setVideoUrl(null);
      setStatus({
        tone: "err",
        text: err?.message || String(err),
      });
    } finally {
      setLoading(false);
    }
  };

  const statusClass =
    status.tone === "ok"
      ? "banner banner--ok"
      : status.tone === "warn"
        ? "banner banner--warn"
        : status.tone === "err"
          ? "banner banner--err"
          : "banner";

  return (
    <div className="shell">
      <div className="bg-grid" aria-hidden />
      <div className="bg-orb bg-orb--1" aria-hidden />
      <div className="bg-orb bg-orb--2" aria-hidden />

      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden />
          <div>
            <p className="brand__eyebrow">local gateway → remote GPU</p>
            <h1 className="brand__title">MouthSync</h1>
          </div>
        </div>
        <p className="header__lead">
          One frame and voice in — short video out. Change the worker URL in
          settings whenever you spin up a new RunPod Pod.
        </p>
      </header>

      <section className="panel panel--settings">
        <button
          type="button"
          className="settings-toggle"
          onClick={() => setSettingsOpen((v) => !v)}
          aria-expanded={settingsOpen}
        >
          <h2 className="panel__title">Worker (RunPod)</h2>
          <span className="settings-toggle__hint">
            {settingsOpen ? "Collapse" : "Expand"}
          </span>
        </button>

        {settingsOpen ? (
          <form className="settings-form" onSubmit={onSaveWorkerSettings}>
            <label className="field">
              <span className="field__label">WORKER_URL</span>
              <input
                className="field__input"
                type="url"
                placeholder="https://pod-id-8000.proxy.runpod.net"
                value={workerUrl}
                onChange={(e) => setWorkerUrl(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                No trailing slash. After a new RunPod Pod, update and click Save.
              </span>
            </label>

            <label className="field">
              <span className="field__label">WORKER_API_KEY</span>
              <input
                className="field__input"
                type="password"
                placeholder="if set on the worker"
                value={workerApiKey}
                onChange={(e) => setWorkerApiKey(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                Secret for X-Worker-Key header. Stored only in this browser.
              </span>
            </label>

            {envWorkerConfigured && !workerUrl.trim() ? (
              <p className="settings-env-note">
                Gateway has <code className="code">WORKER_URL</code> in .env —
                used when the field above is empty.
              </p>
            ) : null}

            <div className="settings-actions">
              <button type="submit" className="btn btn--secondary" disabled={loading}>
                Save
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={loading || testingWorker}
                onClick={onTestWorker}
              >
                {testingWorker ? "Checking…" : "Test connection"}
              </button>
            </div>
          </form>
        ) : null}
      </section>

      <main className="layout">
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__title">Sources</h2>
            <span className="panel__badge">MP4</span>
          </div>

          <form className="form" onSubmit={onSubmit}>
            <FileDropZone
              id="photo"
              label="Portrait"
              hint="JPG / PNG, face close-up"
              accept="image/*"
              disabled={loading}
              file={photo}
              onChange={setPhoto}
            />
            <FileDropZone
              id="audio"
              label="Speech"
              hint="WAV / MP3 / M4A, etc."
              accept="audio/*"
              disabled={loading}
              file={audio}
              onChange={setAudio}
            />

            <div className="form__actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="btn__spinner" aria-hidden />
                    Generating…
                  </>
                ) : (
                  "Generate video"
                )}
              </button>
            </div>
          </form>

          <p className={statusClass} role="status" aria-live="polite">
            {status.text}
          </p>
        </section>

        <section className="panel panel--output">
          <div className="panel__head">
            <h2 className="panel__title">Result</h2>
            {videoUrl ? (
              <a
                className="link-quiet"
                href={videoUrl}
                download="animated.mp4"
                {...(videoUrl.startsWith("/") ? { target: "_blank", rel: "noreferrer" } : {})}
              >
                Download MP4
              </a>
            ) : null}
          </div>

          <div className={`video-frame ${videoUrl ? "" : "video-frame--empty"}`}>
            {videoUrl ? (
              <video
                key={videoUrl}
                className="video"
                src={videoUrl}
                controls
                autoPlay
                playsInline
              />
            ) : (
              <div className="video-placeholder">
                <span className="video-placeholder__ring" aria-hidden />
                <p>Preview appears here after generation.</p>
              </div>
            )}
          </div>
        </section>

        <section className="panel panel--history">
          <div className="panel__head">
            <h2 className="panel__title">History</h2>
            <button
              type="button"
              className="btn btn--ghost btn--small"
              disabled={loading}
              onClick={loadHistory}
            >
              Refresh
            </button>
          </div>

          {historyItems.length === 0 ? (
            <p className="history-empty">
              Nothing yet. After generation, entries appear here and are stored on
              the gateway (<code className="code">gateway/data/history</code>).
            </p>
          ) : (
            <ul className="history-list">
              {historyItems.map((item) => (
                <li
                  key={item.id}
                  className={`history-item ${activeHistoryId === item.id ? "history-item--active" : ""}`}
                >
                  <button
                    type="button"
                    className="history-item__main"
                    onClick={() => playHistoryItem(item)}
                  >
                    <span className="history-item__date">
                      {formatHistoryDate(item.created_at)}
                    </span>
                    <span className="history-item__files">
                      {item.photo_name} · {item.audio_name}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="history-item__delete"
                    title="Delete"
                    onClick={() => onDeleteHistory(item.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>

      <footer className="footer">
        <span className="footer__dot" aria-hidden />
        Browser worker settings override gateway .env. When you change Pods,
        update the URL and click Test connection.
      </footer>
    </div>
  );
}
