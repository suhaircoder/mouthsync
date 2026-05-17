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

function ComparePane({ kind, tag, media, src, meta }) {
  const isPhoto = kind === "photo";

  return (
    <div className="compare__pane">
      <span className="compare__tag">{tag}</span>
      <div
        className={`compare__media${isPhoto ? " compare__media--photo" : " compare__media--audio"}`}
      >
        {src ? (
          isPhoto ? (
            <img src={src} alt={media?.filename || tag} />
          ) : (
            <audio src={src} controls preload="metadata" />
          )
        ) : (
          <span className="compare__empty">—</span>
        )}
      </div>
      {meta ? <p className="compare__meta">{meta}</p> : null}
    </div>
  );
}

export default function LiveComparePreview({
  kind,
  loading,
  error,
  originalUrl,
  originalName,
  data,
}) {
  const isPhoto = kind === "photo";
  const after = data?.after || (isPhoto ? data?.photo : data?.audio);
  const prepEnabled = data?.prep_enabled ?? true;

  const formatMeta = (media, fallbackName) => {
    if (!media && !fallbackName) return null;
    if (media?.size_bytes != null) {
      const name = media.filename || fallbackName;
      const details = isPhoto
        ? `${media.width}×${media.height} · ${formatBytes(media.size_bytes)}`
        : `${formatDuration(media.duration_ms)} · ${formatBytes(media.size_bytes)}`;
      return (
        <>
          {name}
          <br />
          {details}
        </>
      );
    }
    return media?.filename || fallbackName;
  };

  if (error) {
    return <p className="compare__error banner banner--err">{error}</p>;
  }

  return (
    <div className={`compare compare--${kind}${loading ? " compare--loading" : ""}`}>
      <ComparePane
        kind={kind}
        tag="До"
        src={originalUrl}
        media={originalName ? { filename: originalName } : null}
        meta={originalName || null}
      />
      <div className="compare__divider" aria-hidden />
      <ComparePane
        kind={kind}
        tag="После"
        src={after?.data_url}
        media={after}
        meta={
          after
            ? formatMeta(after, null)
            : prepEnabled
              ? "Ожидаем предпросмотр…"
              : "Обработка выключена"
        }
      />
    </div>
  );
}
