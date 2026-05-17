import { useEffect } from "react";

function formatBytes(n) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(ms) {
  if (!ms) return "0:00";
  const sec = Math.round(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function MediaColumn({ kind, label, hint, media, originalSrc }) {
  const isPhoto = kind === "photo";
  const src = originalSrc || media?.data_url;

  return (
    <div className="prep-preview__col">
      <h3 className="prep-preview__label">{label}</h3>
      {hint ? <p className="prep-preview__col-hint">{hint}</p> : null}
      {src ? (
        <>
          {isPhoto ? (
            <div className="prep-preview__media prep-preview__media--photo">
              <img src={src} alt={media?.filename || label} />
            </div>
          ) : (
            <div className="prep-preview__media prep-preview__media--audio">
              <audio src={src} controls preload="metadata" />
            </div>
          )}
          {media ? (
            <p className="prep-preview__meta">
              {media.filename}
              <br />
              {isPhoto
                ? `${media.width}×${media.height} · ${formatBytes(media.size_bytes)}`
                : `${formatDuration(media.duration_ms)} · ${formatBytes(media.size_bytes)}`}
            </p>
          ) : null}
        </>
      ) : (
        <p className="prep-preview__meta">—</p>
      )}
    </div>
  );
}

export default function MediaPrepPreviewModal({
  kind,
  open,
  onClose,
  data,
  loading,
  originalSrc,
  originalName,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  const isPhoto = kind === "photo";
  const title = isPhoto ? "Предпросмотр фото" : "Предпросмотр аудио";
  const prepEnabled = data?.prep_enabled ?? true;
  const before = data?.before;
  const after = data?.after || (isPhoto ? data?.photo : data?.audio);

  const beforeMeta = before || (originalName ? { filename: originalName } : null);

  const subtitle = prepEnabled
    ? "Слева — исходный файл, справа — после настроек на шлюзе (на воркер уйдёт правый вариант)."
    : "Обработка отключена — файлы совпадают с исходником.";

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="media-preview-title"
    >
      <button
        type="button"
        className="modal__backdrop"
        aria-label="Закрыть"
        onClick={onClose}
      />
      <div className="modal__panel modal__panel--wide">
        <header className="modal__header">
          <div>
            <h2 id="media-preview-title" className="modal__title">
              {title}
            </h2>
            <p className="modal__subtitle">{subtitle}</p>
          </div>
          <button
            type="button"
            className="modal__close"
            aria-label="Закрыть"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="modal__body">
          {loading ? (
            <p className="prep-preview__loading">Готовим сравнение на шлюзе…</p>
          ) : (
            <div className="prep-preview">
              <MediaColumn
                kind={kind}
                label="До"
                hint="Загруженный файл без обработки на шлюзе."
                media={beforeMeta}
                originalSrc={originalSrc}
              />
              <MediaColumn
                kind={kind}
                label="После"
                hint={
                  prepEnabled
                    ? isPhoto
                      ? "Масштаб, улучшение, проверка лица → JPEG."
                      : "Задержка, громкость, обрезка и т.д. → WAV."
                    : "Без изменений."
                }
                media={after}
              />
            </div>
          )}
        </div>

        <footer className="modal__footer">
          <div className="modal__footer-right">
            <button type="button" className="btn btn--primary btn--small" onClick={onClose}>
              Закрыть
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
