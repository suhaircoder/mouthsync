import { useModalLock } from "./useModalLock.js";

export default function PrepEditorShell({
  open,
  titleId,
  title,
  fileName,
  onClose,
  onSave,
  onReset,
  loading,
  previewLoading,
  settings,
  preview,
}) {
  useModalLock(open, onClose);

  if (!open) return null;

  return (
    <div className="editor" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="editor__frame">
        <header className="editor__toolbar">
          <button
            type="button"
            className="editor__back"
            aria-label="Закрыть"
            disabled={loading}
            onClick={() => onClose(true)}
          >
            ←
          </button>
          <div className="editor__title-block">
            <h2 id={titleId} className="editor__title">
              {title}
            </h2>
            {fileName ? <p className="editor__file">{fileName}</p> : null}
          </div>
          {previewLoading ? (
            <span className="editor__status" aria-live="polite">
              <span className="btn__spinner" aria-hidden />
              Обновляем…
            </span>
          ) : null}
          <div className="editor__actions">
            <button
              type="button"
              className="btn btn--ghost btn--small"
              disabled={loading}
              onClick={onReset}
            >
              Сбросить
            </button>
            <button
              type="button"
              className="btn btn--secondary btn--small"
              disabled={loading}
              onClick={() => onClose(true)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--primary btn--small"
              disabled={loading}
              onClick={onSave}
            >
              Сохранить
            </button>
          </div>
        </header>

        <div className="editor__main">
          <div className="editor__stage">{preview}</div>
          <aside className="editor__sidebar">{settings}</aside>
        </div>
      </div>
    </div>
  );
}
