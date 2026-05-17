import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { apiHeaders } from "./clientId.js";
import AudioSettingsModal from "./AudioSettingsModal.jsx";
import PhotoSettingsModal from "./PhotoSettingsModal.jsx";
import {
  appendAudioOptionsToFormData,
  audioOptionsForApi,
  audioOptionsFromServer,
  DEFAULT_AUDIO_OPTIONS,
  loadAudioOptions,
  saveAudioOptions,
} from "./audioConfig.js";
import {
  appendPhotoOptionsToFormData,
  DEFAULT_PHOTO_OPTIONS,
  loadPhotoOptions,
  photoOptionsForApi,
  photoOptionsFromServer,
  savePhotoOptions,
} from "./photoConfig.js";
import {
  buildWorkerHeaders,
  hasWorkerConfig,
  loadWorkerConfig,
  saveWorkerConfig,
  workerConfigForApi,
} from "./workerConfig.js";

const API_GENERATE = "/api/generate";
const API_WORKER_STATUS = "/api/worker-status";
const API_HISTORY = "/api/history";
const API_CONFIG = "/api/config";

async function pushConfigToServer(worker, photo, audio) {
  try {
    await fetch(API_CONFIG, {
      method: "PUT",
      headers: {
        ...apiHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        worker: workerConfigForApi(worker),
        photo: photoOptionsForApi(photo),
        audio: audioOptionsForApi(audio),
      }),
    });
  } catch {
    /* offline or mongo unavailable */
  }
}

async function pullConfigFromServer() {
  try {
    const res = await fetch(API_CONFIG, { headers: apiHeaders() });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function apiErrorMessage(body, status) {
  if (!body) return `Ошибка ${status}`;
  try {
    const data = JSON.parse(body);
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* plain text */
  }
  return body.length > 400 ? `${body.slice(0, 400)}…` : body;
}

function formatHistoryDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
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
  const [photoModalOpen, setPhotoModalOpen] = useState(false);
  const [audioModalOpen, setAudioModalOpen] = useState(false);
  const [photoOptions, setPhotoOptions] = useState(() => loadPhotoOptions());
  const [audioOptions, setAudioOptions] = useState(() => loadAudioOptions());
  const photoSnapshotRef = useRef(null);
  const audioSnapshotRef = useRef(null);
  const [workerUrl, setWorkerUrl] = useState("");
  const [workerApiKey, setWorkerApiKey] = useState("");
  const [envWorkerConfigured, setEnvWorkerConfigured] = useState(false);
  const [testingWorker, setTestingWorker] = useState(false);
  const [status, setStatus] = useState({
    tone: "neutral",
    text: "Укажите URL воркера RunPod в настройках ниже (или задайте WORKER_URL в .env).",
  });
  const [videoUrl, setVideoUrl] = useState(null);
  const [historyItems, setHistoryItems] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const prevUrlRef = useRef(null);

  const workerConfig = { workerUrl, workerApiKey };
  const workerHeaders = () => buildWorkerHeaders(workerConfig, apiHeaders());

  const revokePrev = useCallback(() => {
    if (prevUrlRef.current?.startsWith("blob:")) {
      URL.revokeObjectURL(prevUrlRef.current);
    }
    prevUrlRef.current = null;
  }, []);

  useEffect(() => () => revokePrev(), [revokePrev]);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(API_HISTORY, { headers: apiHeaders() });
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

    const hasStoredPhoto =
      typeof localStorage !== "undefined" &&
      localStorage.getItem("mouthsync.photoOptions");
    const hasStoredAudio =
      typeof localStorage !== "undefined" &&
      localStorage.getItem("mouthsync.audioOptions");

    const applyRemote = (remote) => {
      if (!remote?.stored) return;
      if (remote.worker) {
        const w = saveWorkerConfig({
          workerUrl: remote.worker.workerUrl || "",
          workerApiKey: remote.worker.workerApiKey || "",
        });
        setWorkerUrl(w.workerUrl);
        setWorkerApiKey(w.workerApiKey);
      }
      if (remote.photo) {
        const p = savePhotoOptions(remote.photo);
        setPhotoOptions(p);
      }
      if (remote.audio) {
        const a = saveAudioOptions(remote.audio);
        setAudioOptions(a);
      }
    };

    fetch("/health")
      .then((r) => r.json())
      .then((data) => {
        const envOk = Boolean(data.worker_configured);
        setEnvWorkerConfigured(envOk);
        if (!hasStoredPhoto && data.photo_prep) {
          const fromServer = photoOptionsFromServer(data.photo_prep);
          if (fromServer) setPhotoOptions(fromServer);
        }
        if (!hasStoredAudio && data.audio_prep) {
          const fromServer = audioOptionsFromServer(data.audio_prep);
          if (fromServer) setAudioOptions(fromServer);
        }
        if (saved.workerUrl || envOk) {
          setStatus({
            tone: "neutral",
            text: saved.workerUrl
              ? "URL воркера загружен из настроек браузера."
              : "Используется WORKER_URL из .env на шлюзе.",
          });
        }
      })
      .catch(() => {});

    pullConfigFromServer().then((remote) => {
      if (remote?.stored) {
        applyRemote(remote);
        setStatus({
          tone: "neutral",
          text: "Настройки загружены из MongoDB.",
        });
      }
    });

    loadHistory();
  }, [loadHistory]);

  const playHistoryItem = (item) => {
    revokePrev();
    setActiveHistoryId(item.id);
    setVideoUrl(item.video_url);
    setStatus({
      tone: "neutral",
      text: `Из истории: ${item.photo_name} + ${item.audio_name}`,
    });
  };

  const onDeleteHistory = async (id) => {
    try {
      const res = await fetch(`${API_HISTORY}/${id}`, {
        method: "DELETE",
        headers: apiHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (activeHistoryId === id) {
        revokePrev();
        setVideoUrl(null);
        setActiveHistoryId(null);
      }
      await loadHistory();
      setStatus({ tone: "ok", text: "Запись удалена из истории." });
    } catch (err) {
      setStatus({
        tone: "err",
        text: err?.message || String(err),
      });
    }
  };

  const setPhotoField = (key, value) => {
    setPhotoOptions((prev) => ({ ...prev, [key]: value }));
  };

  const openPhotoModal = () => {
    if (!photo) {
      setStatus({ tone: "warn", text: "Сначала загрузите портрет." });
      return;
    }
    photoSnapshotRef.current = { ...photoOptions };
    setPhotoModalOpen(true);
  };

  const closePhotoModal = (discard = false) => {
    if (discard && photoSnapshotRef.current) {
      setPhotoOptions(photoSnapshotRef.current);
    }
    photoSnapshotRef.current = null;
    setPhotoModalOpen(false);
  };

  const onSavePhotoSettings = async () => {
    const saved = savePhotoOptions(photoOptions);
    setPhotoOptions(saved);
    await pushConfigToServer({ workerUrl, workerApiKey }, saved, audioOptions);
    photoSnapshotRef.current = null;
    setPhotoModalOpen(false);
    setStatus({
      tone: "ok",
      text: "Настройки фото сохранены (браузер и MongoDB).",
    });
  };

  const onResetPhotoSettings = () => {
    setPhotoOptions({ ...DEFAULT_PHOTO_OPTIONS });
  };

  const setAudioField = (key, value) => {
    setAudioOptions((prev) => ({ ...prev, [key]: value }));
  };

  const openAudioModal = () => {
    if (!audio) {
      setStatus({ tone: "warn", text: "Сначала загрузите аудио." });
      return;
    }
    audioSnapshotRef.current = { ...audioOptions };
    setAudioModalOpen(true);
  };

  const closeAudioModal = (discard = false) => {
    if (discard && audioSnapshotRef.current) {
      setAudioOptions(audioSnapshotRef.current);
    }
    audioSnapshotRef.current = null;
    setAudioModalOpen(false);
  };

  const onSaveAudioSettings = async () => {
    const saved = saveAudioOptions(audioOptions);
    setAudioOptions(saved);
    await pushConfigToServer({ workerUrl, workerApiKey }, photoOptions, saved);
    audioSnapshotRef.current = null;
    setAudioModalOpen(false);
    setStatus({
      tone: "ok",
      text: "Настройки аудио сохранены (браузер и MongoDB).",
    });
  };

  const onResetAudioSettings = () => {
    setAudioOptions({ ...DEFAULT_AUDIO_OPTIONS });
  };

  const photoSettingsSummary = !photoOptions.prepEnabled
    ? "Обработка выкл — исходный файл"
    : photoOptions.faceCheckEnabled
      ? `Лицо ${Math.round(photoOptions.minFaceSizeRatio * 100)}%${photoOptions.faceAutoCrop ? " · обрезка" : ""} · JPEG ${photoOptions.jpegQuality}`
      : `Лицо: выкл · ярк. ${photoOptions.brightness.toFixed(1)}`;

  const audioSettingsSummary = !audioOptions.prepEnabled
    ? "Обработка выкл — исходный файл"
    : [
        Math.abs(audioOptions.playbackSpeed - 1) > 0.01
          ? `${Math.round(audioOptions.playbackSpeed * 100)}%`
          : null,
        audioOptions.delayMs > 0 ? `задержка ${audioOptions.delayMs} мс` : null,
        `громк. ${audioOptions.gainDb >= 0 ? "+" : ""}${audioOptions.gainDb.toFixed(0)} dB`,
        audioOptions.trimSilence ? "обрезка тишины" : null,
      ]
        .filter(Boolean)
        .join(" · ");

  const onSaveWorkerSettings = async (e) => {
    e.preventDefault();
    const saved = saveWorkerConfig({ workerUrl, workerApiKey });
    setWorkerUrl(saved.workerUrl);
    setWorkerApiKey(saved.workerApiKey);
    await pushConfigToServer(saved, photoOptions, audioOptions);
    setStatus({
      tone: "ok",
      text: "Настройки воркера сохранены (браузер и MongoDB).",
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
          text: `Воркер доступен: ${data.worker_url}`,
        });
      } else {
        setStatus({
          tone: "err",
          text: data.detail || `Проверка не прошла (${res.status})`,
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
        text: "Нужны оба файла: изображение лица и аудио.",
      });
      return;
    }

    if (!hasWorkerConfig(workerConfig, envWorkerConfigured)) {
      setStatus({
        tone: "warn",
        text: "Сначала укажите URL воркера в настройках или в .env.",
      });
      setSettingsOpen(true);
      return;
    }

    setLoading(true);
    setStatus({
      tone: "neutral",
      text: "Отправляем на воркер… это может занять минуту или больше.",
    });

    const form = new FormData();
    form.append("photo", photo);
    form.append("audio", audio);
    appendPhotoOptionsToFormData(form, photoOptions);
    appendAudioOptionsToFormData(form, audioOptions);
    savePhotoOptions(photoOptions);
    saveAudioOptions(audioOptions);
    await pushConfigToServer({ workerUrl, workerApiKey }, photoOptions, audioOptions);

    try {
      const res = await fetch(API_GENERATE, {
        method: "POST",
        headers: workerHeaders(),
        body: form,
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(apiErrorMessage(t, res.status));
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
          ? "Готово. Видео сохранено в истории на шлюзе."
          : "Готово. Ниже результат — с автозапуском превью.",
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
            <p className="brand__eyebrow">локальный шлюз → удалённый GPU</p>
            <h1 className="brand__title">MouthSync</h1>
          </div>
        </div>
        <p className="header__lead">
          Один кадр и голос — на выходе короткое видео. URL воркера можно менять в
          настройках при каждом новом Pod на RunPod.
        </p>
      </header>

      <section className="panel panel--settings">
        <button
          type="button"
          className="settings-toggle"
          onClick={() => setSettingsOpen((v) => !v)}
          aria-expanded={settingsOpen}
        >
          <h2 className="panel__title">Воркер (RunPod)</h2>
          <span className="settings-toggle__hint">
            {settingsOpen ? "Свернуть" : "Развернуть"}
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
                Без слэша в конце. После нового Pod в RunPod обновите и нажмите «Сохранить».
              </span>
            </label>

            <label className="field">
              <span className="field__label">WORKER_API_KEY</span>
              <input
                className="field__input"
                type="password"
                placeholder="если задан на воркере"
                value={workerApiKey}
                onChange={(e) => setWorkerApiKey(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                Секрет для заголовка X-Worker-Key. Хранится только в этом браузере.
              </span>
            </label>

            {envWorkerConfigured && !workerUrl.trim() ? (
              <p className="settings-env-note">
                На шлюзе задан <code className="code">WORKER_URL</code> в .env —
                будет использован, если поле выше пустое.
              </p>
            ) : null}

            <div className="settings-actions">
              <button type="submit" className="btn btn--secondary" disabled={loading}>
                Сохранить
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={loading || testingWorker}
                onClick={onTestWorker}
              >
                {testingWorker ? "Проверка…" : "Проверить связь"}
              </button>
            </div>
          </form>
        ) : null}
      </section>

      <main className="layout">
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__title">Источники</h2>
            <span className="panel__badge">MP4</span>
          </div>

          <form className="form" onSubmit={onSubmit}>
            <FileDropZone
              id="photo"
              label="Портрет"
              hint="JPG / PNG, лицо крупным планом"
              accept="image/*"
              disabled={loading}
              file={photo}
              onChange={setPhoto}
            />
            <FileDropZone
              id="audio"
              label="Речь"
              hint="WAV / MP3 / M4A и др."
              accept="audio/*"
              disabled={loading}
              file={audio}
              onChange={setAudio}
            />

            <div className="photo-settings-bar">
              <label className="field__checkbox field__checkbox--inline">
                <input
                  type="checkbox"
                  checked={photoOptions.prepEnabled}
                  disabled={loading}
                  onChange={(e) => {
                    const next = { ...photoOptions, prepEnabled: e.target.checked };
                    setPhotoOptions(next);
                    savePhotoOptions(next);
                  }}
                />
                Обработка фото
              </label>
              <button
                type="button"
                className="btn btn--ghost btn--small"
                disabled={loading || !photo}
                onClick={openPhotoModal}
              >
                Редактор
              </button>
              <span className="photo-settings-bar__summary">{photoSettingsSummary}</span>
            </div>

            <div className="photo-settings-bar">
              <label className="field__checkbox field__checkbox--inline">
                <input
                  type="checkbox"
                  checked={audioOptions.prepEnabled}
                  disabled={loading}
                  onChange={(e) => {
                    const next = { ...audioOptions, prepEnabled: e.target.checked };
                    setAudioOptions(next);
                    saveAudioOptions(next);
                  }}
                />
                Обработка аудио
              </label>
              <button
                type="button"
                className="btn btn--ghost btn--small"
                disabled={loading || !audio}
                onClick={openAudioModal}
              >
                Редактор
              </button>
              <span className="photo-settings-bar__summary">{audioSettingsSummary}</span>
            </div>

            <div className="form__actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="btn__spinner" aria-hidden />
                    Генерация…
                  </>
                ) : (
                  "Собрать видео"
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
            <h2 className="panel__title">Результат</h2>
            {videoUrl ? (
              <a
                className="link-quiet"
                href={videoUrl}
                download="animated.mp4"
                {...(videoUrl.startsWith("/") ? { target: "_blank", rel: "noreferrer" } : {})}
              >
                Скачать MP4
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
                <p>Превью появится здесь после генерации.</p>
              </div>
            )}
          </div>
        </section>

        <section className="panel panel--history">
          <div className="panel__head">
            <h2 className="panel__title">История</h2>
            <button
              type="button"
              className="btn btn--ghost btn--small"
              disabled={loading}
              onClick={loadHistory}
            >
              Обновить
            </button>
          </div>

          {historyItems.length === 0 ? (
            <p className="history-empty">
              Пока пусто. После генерации записи появятся здесь и сохранятся в
              MongoDB (файлы — GridFS).
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
                    title="Удалить"
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
        Настройки воркера в браузере перекрывают .env на шлюзе. При смене Pod
        обновите URL и нажмите «Проверить связь».
      </footer>

      <PhotoSettingsModal
        open={photoModalOpen}
        onClose={closePhotoModal}
        photoOptions={photoOptions}
        setPhotoField={setPhotoField}
        onSave={onSavePhotoSettings}
        onReset={onResetPhotoSettings}
        loading={loading}
        photoFile={photo}
        photoFileName={photo?.name}
      />
      <AudioSettingsModal
        open={audioModalOpen}
        onClose={closeAudioModal}
        audioOptions={audioOptions}
        setAudioField={setAudioField}
        onSave={onSaveAudioSettings}
        onReset={onResetAudioSettings}
        loading={loading}
        audioFile={audio}
        audioFileName={audio?.name}
      />
    </div>
  );
}
