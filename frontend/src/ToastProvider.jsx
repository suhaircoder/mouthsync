import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import "./Toast.css";

const ToastContext = createContext(null);

const DEFAULT_DURATION = {
  ok: 5000,
  warn: 7000,
  err: 12000,
  neutral: 4500,
};

const LABELS = {
  ok: "Готово",
  warn: "Внимание",
  err: "Ошибка",
  neutral: "Сообщение",
};

let nextId = 0;

function ToastItem({ toast, onDismiss }) {
  const icon =
    toast.tone === "ok" ? "✓" : toast.tone === "err" ? "!" : toast.tone === "warn" ? "!" : "…";

  return (
    <div
      className={`toast toast--${toast.tone}`}
      role={toast.tone === "err" ? "alert" : "status"}
    >
      <span className="toast__icon" aria-hidden>
        {icon}
      </span>
      <div className="toast__body">
        <span className="toast__label">{LABELS[toast.tone] || LABELS.neutral}</span>
        <p className="toast__text">{toast.text}</p>
      </div>
      <button
        type="button"
        className="toast__close"
        aria-label="Закрыть"
        onClick={onDismiss}
      >
        ×
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef(new Map());

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const dismissAll = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
    setToasts([]);
  }, []);

  const push = useCallback(
    (tone, text, options = {}) => {
      const id = options.id ?? `toast-${++nextId}`;
      const persistent = Boolean(options.persistent);
      const duration = persistent
        ? 0
        : (options.duration ?? DEFAULT_DURATION[tone] ?? DEFAULT_DURATION.neutral);

      setToasts((prev) => {
        const filtered = prev.filter((t) => t.id !== id);
        return [...filtered, { id, tone, text, persistent }];
      });

      const existing = timersRef.current.get(id);
      if (existing) clearTimeout(existing);

      if (!persistent && duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration);
        timersRef.current.set(id, timer);
      }

      return id;
    },
    [dismiss],
  );

  const api = useMemo(
    () => ({
      push,
      dismiss,
      dismissAll,
      success: (text, options) => push("ok", text, options),
      error: (text, options) => push("err", text, options),
      warn: (text, options) => push("warn", text, options),
      info: (text, options) => push("neutral", text, options),
      progress: (text, options) =>
        push("neutral", text, { id: "progress", persistent: true, ...options }),
      clearProgress: () => dismiss("progress"),
    }),
    [push, dismiss, dismissAll],
  );

  useEffect(
    () => () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
    },
    [],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-viewport" aria-live="polite" aria-relevant="additions">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
