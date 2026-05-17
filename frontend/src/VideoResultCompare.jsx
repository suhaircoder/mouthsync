export default function VideoResultCompare({ stage1Url, refinedUrl }) {
  if (!stage1Url || !refinedUrl) return null;

  return (
    <div className="video-compare" role="group" aria-label="Сравнение этапов">
      <div className="video-compare__pane">
        <span className="video-compare__tag">Первый этап</span>
        <video
          className="video video-compare__player"
          src={stage1Url}
          controls
          playsInline
          preload="metadata"
        />
      </div>
      <div className="video-compare__divider" aria-hidden="true" />
      <div className="video-compare__pane">
        <span className="video-compare__tag">Второй этап</span>
        <video
          className="video video-compare__player"
          src={refinedUrl}
          controls
          playsInline
          preload="metadata"
        />
      </div>
    </div>
  );
}
