export default function EditorSection({ title, hint, children, muted }) {
  return (
    <section className={`editor-section${muted ? " editor-section--muted" : ""}`}>
      {title ? <h3 className="editor-section__title">{title}</h3> : null}
      {hint ? <p className="editor-section__hint">{hint}</p> : null}
      <div className="editor-section__body">{children}</div>
    </section>
  );
}
