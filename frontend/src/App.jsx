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
import { useToast } from "./ToastProvider.jsx";
import {
  buildWorkerHeaders,
  hasWav2lipConfig,
  hasWorkerConfig,
  hasLocalWorkerUrls,
  loadWorkerConfig,
  mergeWorkerWithRemote,
  saveWorkerConfig,
  workerConfigForApi,
} from "./workerConfig.js";

const API_GENERATE = "/api/generate";
const API_WORKER_STATUS = "/api/worker-status";
const API_WAV2LIP_WORKER_STATUS = "/api/wav2lip-worker-status";
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

function videoDownloadProps(url, filename) {
  const isRemote = url.startsWith("/");
  return {
    href: url,
    download: filename,
    ...(isRemote ? { target: "_blank", rel: "noreferrer" } : {}),
  };
}

function ResultStage({ title, videoUrl, downloadName, loading, pendingHint }) {
  return (
    <div className={`result-stage ${loading ? "result-stage--loading" : ""}`}>
      <div className="result-stage__head">
        <h3 className="result-stage__title">{title}</h3>
        {videoUrl && !loading ? (
          <a className="link-quiet" {...videoDownloadProps(videoUrl, downloadName)}>
            Скачать
          </a>
        ) : null}
      </div>
      <div className={`video-frame ${videoUrl || loading || pendingHint ? "" : "video-frame--empty"}`}>
        {loading ? (
          <div className="result-stage__loading">
            <span className="btn__spinner" aria-hidden />
            <p>Обработка…</p>
          </div>
        ) : videoUrl ? (
          <video
            key={videoUrl}
            className="video"
            src={videoUrl}
            controls
            playsInline
            preload="metadata"
          />
        ) : pendingHint ? (
          <div className="video-placeholder video-placeholder--compact">
            <p>{pendingHint}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
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
  const [wav2lipWorkerUrl, setWav2lipWorkerUrl] = useState("");
  const [wav2lipWorkerApiKey, setWav2lipWorkerApiKey] = useState("");
  const [envWorkerConfigured, setEnvWorkerConfigured] = useState(false);
  const [envWav2lipConfigured, setEnvWav2lipConfigured] = useState(false);
  const [testingWorker, setTestingWorker] = useState(false);
  const [testingWav2lip, setTestingWav2lip] = useState(false);
  const toast = useToast();
  const [stage1Url, setStage1Url] = useState(null);
  const [refinedUrl, setRefinedUrl] = useState(null);
  const [refining, setRefining] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const blobUrlsRef = useRef({ stage1: null, refined: null });
  const skipWorkerAutosaveRef = useRef(true);

  const workerConfig = {
    workerUrl,
    workerApiKey,
    wav2lipWorkerUrl,
    wav2lipWorkerApiKey,
  };
  const workerHeaders = () => buildWorkerHeaders(workerConfig, apiHeaders());

  const activeHistoryItem = historyItems.find((item) => item.id === activeHistoryId);
  const hasRefinedResult = Boolean(refinedUrl);
  const stage1Ready = Boolean(stage1Url && activeHistoryId);
  const alreadyRefined = Boolean(hasRefinedResult || activeHistoryItem?.refined);
  const refineServerReady = hasWav2lipConfig(workerConfig, envWav2lipConfigured);
  const refineAvailable = stage1Ready && !alreadyRefined && refineServerReady;
  const refineDisabled = loading || refining || !refineAvailable;

  const refineHint = (() => {
    if (refining) return null;
    if (alreadyRefined) {
      return "Второй этап уже выполнен — оба видео в блоке «Результат».";
    }
    if (!refineServerReady) {
      return "Для этапа 2 укажите сервер улучшения губ в настройках.";
    }
    if (!stage1Ready) {
      return "Этап 2 станет доступен после создания видео на этапе 1.";
    }
    if (loading) return "Дождитесь окончания этапа 1.";
    return "Улучшает губы в уже созданном видео; оба варианта сохранятся для сравнения.";
  })();

  const revokeBlob = useCallback((slot) => {
    const url = blobUrlsRef.current[slot];
    if (url?.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
    blobUrlsRef.current[slot] = null;
  }, []);

  const revokeAllBlobs = useCallback(() => {
    revokeBlob("stage1");
    revokeBlob("refined");
  }, [revokeBlob]);

  const trackBlob = useCallback((slot, url) => {
    revokeBlob(slot);
    if (url?.startsWith("blob:")) {
      blobUrlsRef.current[slot] = url;
    }
  }, [revokeBlob]);

  const clearResults = useCallback(() => {
    revokeAllBlobs();
    setStage1Url(null);
    setRefinedUrl(null);
  }, [revokeAllBlobs]);

  useEffect(() => () => revokeAllBlobs(), [revokeAllBlobs]);

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
    setWav2lipWorkerUrl(saved.wav2lipWorkerUrl);
    setWav2lipWorkerApiKey(saved.wav2lipWorkerApiKey);

    const hasStoredPhoto =
      typeof localStorage !== "undefined" &&
      localStorage.getItem("mouthsync.photoOptions");
    const hasStoredAudio =
      typeof localStorage !== "undefined" &&
      localStorage.getItem("mouthsync.audioOptions");

    const applyRemote = (remote) => {
      if (!remote?.stored) return;
      if (remote.worker) {
        const merged = mergeWorkerWithRemote(saved, remote.worker);
        const w = saveWorkerConfig(merged);
        setWorkerUrl(w.workerUrl);
        setWorkerApiKey(w.workerApiKey);
        setWav2lipWorkerUrl(w.wav2lipWorkerUrl);
        setWav2lipWorkerApiKey(w.wav2lipWorkerApiKey);
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
        const envW2l = Boolean(data.wav2lip_worker_configured);
        setEnvWorkerConfigured(envOk);
        setEnvWav2lipConfigured(envW2l);
        if (!hasStoredPhoto && data.photo_prep) {
          const fromServer = photoOptionsFromServer(data.photo_prep);
          if (fromServer) setPhotoOptions(fromServer);
        }
        if (!hasStoredAudio && data.audio_prep) {
          const fromServer = audioOptionsFromServer(data.audio_prep);
          if (fromServer) setAudioOptions(fromServer);
        }
        if (saved.workerUrl || envOk) {
          toast.info(
            saved.workerUrl
              ? "Адрес сервера взят из сохранённых настроек."
              : "Используется адрес сервера из конфигурации приложения.",
          );
        }
      })
      .catch(() => {});

    pullConfigFromServer().then((remote) => {
      if (!remote?.stored) return;
      const hadLocal = hasLocalWorkerUrls(saved);
      applyRemote(remote);
      if (!hadLocal && hasLocalWorkerUrls(loadWorkerConfig())) {
        toast.info("Адреса серверов подставлены из сохранённых настроек.");
      }
    });

    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (skipWorkerAutosaveRef.current) {
      skipWorkerAutosaveRef.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      saveWorkerConfig({
        workerUrl,
        workerApiKey,
        wav2lipWorkerUrl,
        wav2lipWorkerApiKey,
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [workerUrl, workerApiKey, wav2lipWorkerUrl, wav2lipWorkerApiKey]);

  const playHistoryItem = (item) => {
    revokeAllBlobs();
    setActiveHistoryId(item.id);
    const s1 = item.video_stage1_url || item.video_url;
    setStage1Url(s1);
    if (item.refined && item.video_refined_url) {
      setRefinedUrl(item.video_refined_url);
    } else {
      setRefinedUrl(null);
    }
    toast.info(
      `Из истории: ${item.photo_name} + ${item.audio_name}${
        item.refined ? " (оба этапа)" : ""
      }`,
    );
  };

  const onDeleteHistory = async (id) => {
    try {
      const res = await fetch(`${API_HISTORY}/${id}`, {
        method: "DELETE",
        headers: apiHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (activeHistoryId === id) {
        clearResults();
        setActiveHistoryId(null);
      }
      await loadHistory();
      toast.success("Запись удалена из истории.");
    } catch (err) {
      toast.error(err?.message || String(err));
    }
  };

  const setPhotoField = (key, value) => {
    setPhotoOptions((prev) => ({ ...prev, [key]: value }));
  };

  const openPhotoModal = () => {
    if (!photo) {
      toast.warn("Сначала загрузите портрет.");
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
    await pushConfigToServer(workerConfig, saved, audioOptions);
    photoSnapshotRef.current = null;
    setPhotoModalOpen(false);
    toast.success("Настройки фото сохранены.");
  };

  const onResetPhotoSettings = () => {
    setPhotoOptions({ ...DEFAULT_PHOTO_OPTIONS });
  };

  const setAudioField = (key, value) => {
    setAudioOptions((prev) => ({ ...prev, [key]: value }));
  };

  const openAudioModal = () => {
    if (!audio) {
      toast.warn("Сначала загрузите аудио.");
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
    await pushConfigToServer(workerConfig, photoOptions, saved);
    audioSnapshotRef.current = null;
    setAudioModalOpen(false);
    toast.success("Настройки аудио сохранены.");
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
    const saved = saveWorkerConfig(workerConfig);
    setWorkerUrl(saved.workerUrl);
    setWorkerApiKey(saved.workerApiKey);
    setWav2lipWorkerUrl(saved.wav2lipWorkerUrl);
    setWav2lipWorkerApiKey(saved.wav2lipWorkerApiKey);
    await pushConfigToServer(saved, photoOptions, audioOptions);
    toast.success("Настройки серверов сохранены.");
  };

  const onTestWorker = async () => {
    const saved = saveWorkerConfig(workerConfig);
    setTestingWorker(true);
    try {
      const res = await fetch(API_WORKER_STATUS, {
        headers: buildWorkerHeaders(saved, apiHeaders()),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        toast.success("Связь с основным сервером установлена.");
      } else {
        toast.error(data.detail || `Проверка не прошла (${res.status})`);
      }
    } catch (err) {
      toast.error(err?.message || String(err));
    } finally {
      setTestingWorker(false);
    }
  };

  const onTestWav2lip = async () => {
    const saved = saveWorkerConfig(workerConfig);
    setTestingWav2lip(true);
    try {
      const res = await fetch(API_WAV2LIP_WORKER_STATUS, {
        headers: buildWorkerHeaders(saved, apiHeaders()),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        const backend = data.worker?.backend;
        if (backend === "sadtalker") {
          toast.error(
            "Это адрес этапа 1. Для этапа 2 укажите отдельный сервер улучшения губ.",
          );
        } else if (backend && backend !== "wav2lip") {
          toast.error(`Этот сервер не подходит для этапа 2 (тип: ${backend}).`);
        } else if (backend === "wav2lip" && data.worker?.ready === false) {
          toast.warn("Сервер Wav2Lip доступен, но модели ещё загружаются. Подождите минуту.");
        } else if (!backend) {
          toast.error("Этот сервер не поддерживает этап 2. Нужен отдельный Wav2Lip-сервер.");
        } else {
          toast.success("Сервер для этапа 2 готов.");
        }
      } else {
        toast.error(data.detail || "Не удалось проверить сервер улучшения губ.");
      }
    } catch (err) {
      toast.error(err?.message || String(err));
    } finally {
      setTestingWav2lip(false);
    }
  };

  const onRefine = async () => {
    if (!activeHistoryId) return;
    if (!hasWav2lipConfig(workerConfig, envWav2lipConfigured)) {
      toast.warn("Укажите адрес сервера для второго этапа в настройках.");
      setSettingsOpen(true);
      return;
    }

    const saved = saveWorkerConfig(workerConfig);
    await pushConfigToServer(saved, photoOptions, audioOptions);

    setRefining(true);
    toast.progress("Второй этап: улучшение губ… это может занять несколько минут.");

    try {
      const res = await fetch(`${API_HISTORY}/${activeHistoryId}/refine`, {
        method: "POST",
        headers: buildWorkerHeaders(saved, apiHeaders()),
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(apiErrorMessage(t, res.status));
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      trackBlob("refined", url);
      setRefinedUrl(url);
      await loadHistory();
      toast.success("Второй этап готов. Сравните оба варианта ниже.");
    } catch (err) {
      toast.error(err?.message || String(err));
    } finally {
      setRefining(false);
      toast.clearProgress();
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!photo || !audio) {
      toast.warn("Нужны оба файла: изображение лица и аудио.");
      return;
    }

    if (!hasWorkerConfig(workerConfig, envWorkerConfigured)) {
      toast.warn("Сначала укажите адрес сервера генерации в настройках.");
      setSettingsOpen(true);
      return;
    }

    setLoading(true);
    toast.progress("Первый этап: создание видео… это может занять минуту или больше.");

    const form = new FormData();
    form.append("photo", photo);
    form.append("audio", audio);
    appendPhotoOptionsToFormData(form, photoOptions);
    appendAudioOptionsToFormData(form, audioOptions);
    savePhotoOptions(photoOptions);
    saveAudioOptions(audioOptions);
    const saved = saveWorkerConfig(workerConfig);
    await pushConfigToServer(saved, photoOptions, audioOptions);

    try {
      const res = await fetch(API_GENERATE, {
        method: "POST",
        headers: buildWorkerHeaders(saved, apiHeaders()),
        body: form,
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(apiErrorMessage(t, res.status));
      }
      const historyId = res.headers.get("X-History-Id");
      const blob = await res.blob();
      revokeAllBlobs();
      const url = URL.createObjectURL(blob);
      trackBlob("stage1", url);
      setStage1Url(url);
      setRefinedUrl(null);
      setActiveHistoryId(historyId);
      await loadHistory();
      toast.success(
        historyId
          ? "Первый этап готов. Просмотрите результат и при необходимости запустите улучшение губ."
          : "Первый этап готов. Ниже превью — при необходимости запустите улучшение губ.",
      );
    } catch (err) {
      clearResults();
      toast.error(err?.message || String(err));
    } finally {
      setLoading(false);
      toast.clearProgress();
    }
  };

  return (
    <div className="shell">
      <div className="bg-grid" aria-hidden />
      <div className="bg-orb bg-orb--1" aria-hidden />
      <div className="bg-orb bg-orb--2" aria-hidden />

      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden />
          <div>
            <p className="brand__eyebrow">фото и голос → говорящее видео</p>
            <h1 className="brand__title">MouthSync</h1>
          </div>
        </div>
        <p className="header__lead">
          Загрузите портрет и аудио — получите короткое видео. Адрес сервера можно
          менять в настройках при смене облачного инстанса.
        </p>
      </header>

      <section className="panel panel--settings">
        <button
          type="button"
          className="settings-toggle"
          onClick={() => setSettingsOpen((v) => !v)}
          aria-expanded={settingsOpen}
        >
          <h2 className="panel__title">Серверы</h2>
          <span className="settings-toggle__hint">
            {settingsOpen ? "Свернуть" : "Развернуть"}
          </span>
        </button>

        {settingsOpen ? (
          <form className="settings-form" onSubmit={onSaveWorkerSettings}>
            <label className="field">
              <span className="field__label">Основной сервер (первый этап)</span>
              <input
                className="field__input"
                type="url"
                placeholder="https://sadtalker-pod-8000.proxy.runpod.net"
                value={workerUrl}
                onChange={(e) => setWorkerUrl(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                Первый этап: фото + аудио → видео. Без слэша в конце.
              </span>
            </label>

            <label className="field">
              <span className="field__label">Сервер улучшения губ (второй этап)</span>
              <input
                className="field__input"
                type="url"
                placeholder="https://wav2lip-pod-8000.proxy.runpod.net"
                value={wav2lipWorkerUrl}
                onChange={(e) => setWav2lipWorkerUrl(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                Необязательно. Второй этап запускается кнопкой под превью.
              </span>
            </label>

            <label className="field">
              <span className="field__label">Ключ доступа к основному серверу</span>
              <input
                className="field__input"
                type="password"
                placeholder="если требуется сервером"
                value={workerApiKey}
                onChange={(e) => setWorkerApiKey(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
              <span className="field__hint">
                Хранится только в этом браузере на вашем устройстве.
              </span>
            </label>

            <label className="field">
              <span className="field__label">Ключ для второго сервера (если другой)</span>
              <input
                className="field__input"
                type="password"
                placeholder="необязательно"
                value={wav2lipWorkerApiKey}
                onChange={(e) => setWav2lipWorkerApiKey(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
            </label>

            {envWorkerConfigured && !workerUrl.trim() ? (
              <p className="settings-env-note">
                Адрес основного сервера задан администратором — подставится, если поле
                выше пустое.
              </p>
            ) : null}
            {envWav2lipConfigured && !wav2lipWorkerUrl.trim() ? (
              <p className="settings-env-note">
                Адрес сервера для второго этапа задан администратором.
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
                {testingWorker ? "…" : "Проверить основной"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={loading || testingWav2lip}
                onClick={onTestWav2lip}
              >
                {testingWav2lip ? "…" : "Проверить второй"}
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

            <div className="form__actions form__actions--pipeline">
              <div className="pipeline-step">
                <span className="pipeline-step__label">Этап 1</span>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={loading || refining}
                >
                  {loading ? (
                    <>
                      <span className="btn__spinner" aria-hidden />
                      Создание…
                    </>
                  ) : (
                    "Создать видео"
                  )}
                </button>
              </div>
              <div className="pipeline-step">
                <span className="pipeline-step__label">Этап 2</span>
                <button
                  type="button"
                  className="btn btn--stage2"
                  disabled={refineDisabled}
                  title={refineDisabled && refineHint ? refineHint : undefined}
                  onClick={onRefine}
                >
                  {refining ? (
                    <>
                      <span className="btn__spinner" aria-hidden />
                      Улучшение…
                    </>
                  ) : (
                    "Улучшить губы"
                  )}
                </button>
              </div>
            </div>
            {refineHint ? (
              <p className="form__pipeline-hint">{refineHint}</p>
            ) : null}
          </form>
        </section>

        <section className="panel panel--output">
          <div className="panel__head">
            <h2 className="panel__title">Результат</h2>
          </div>

          <div className="result-stack">
            {stage1Url ? (
              <ResultStage
                title="Этап 1 — создание видео"
                videoUrl={stage1Url}
                downloadName="etap-1.mp4"
              />
            ) : (
              <div className="video-frame video-frame--empty">
                <div className="video-placeholder">
                  <span className="video-placeholder__ring" aria-hidden />
                  <p>Превью первого этапа появится здесь.</p>
                </div>
              </div>
            )}

            {refinedUrl || refining ? (
              <ResultStage
                title="Этап 2 — улучшение губ"
                videoUrl={refinedUrl}
                downloadName="etap-2.mp4"
                loading={refining}
              />
            ) : stage1Ready && !alreadyRefined && refineServerReady ? (
              <ResultStage
                title="Этап 2 — улучшение губ"
                pendingHint="Нажмите «Улучшить губы» после просмотра первого видео."
              />
            ) : null}
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
              Пока пусто. После генерации ваши работы появятся здесь.
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
                      {item.refined ? " · улучшено" : ""}
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
