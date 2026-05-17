import { useEffect, useRef, useState } from "react";
import { apiHeaders } from "./clientId.js";

function parseApiError(body, status) {
  if (!body) return `Ошибка ${status}`;
  try {
    const data = JSON.parse(body);
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* plain text */
  }
  return body.length > 400 ? `${body.slice(0, 400)}…` : body;
}

export function usePrepPreview({
  open,
  mediaFile,
  mediaFieldName,
  previewEndpoint,
  options,
  appendOptions,
  debounceMs = 450,
}) {
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [originalUrl, setOriginalUrl] = useState(null);
  const abortRef = useRef(null);
  const optionsKey = JSON.stringify(options);

  useEffect(() => {
    if (!open || !mediaFile) {
      setOriginalUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return undefined;
    }
    const url = URL.createObjectURL(mediaFile);
    setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [open, mediaFile]);

  useEffect(() => {
    if (!open) {
      setPreviewData(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return undefined;
    }
    if (!mediaFile) {
      setPreviewData(null);
      setPreviewError("Загрузите файл, чтобы увидеть предпросмотр.");
      setPreviewLoading(false);
      return undefined;
    }

    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setPreviewLoading(true);
      setPreviewError(null);

      const form = new FormData();
      form.append(mediaFieldName, mediaFile);
      appendOptions(form, options);

      try {
        const res = await fetch(previewEndpoint, {
          method: "POST",
          headers: apiHeaders(),
          body: form,
          signal: ac.signal,
        });
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          throw new Error(parseApiError(t, res.status));
        }
        const data = await res.json();
        if (!ac.signal.aborted) setPreviewData(data);
      } catch (err) {
        if (err?.name === "AbortError") return;
        if (!ac.signal.aborted) {
          setPreviewData(null);
          setPreviewError(err?.message || String(err));
        }
      } finally {
        if (!ac.signal.aborted) setPreviewLoading(false);
      }
    }, debounceMs);

    return () => {
      window.clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [
    open,
    mediaFile,
    mediaFieldName,
    previewEndpoint,
    debounceMs,
    optionsKey,
    appendOptions,
  ]);

  return { previewData, previewLoading, previewError, originalUrl };
}
