import EditorSection from "./EditorSection.jsx";
import LiveComparePreview from "./LiveComparePreview.jsx";
import PrepEditorShell from "./PrepEditorShell.jsx";
import { appendAudioOptionsToFormData } from "./audioConfig.js";
import { usePrepPreview } from "./usePrepPreview.js";

const API_PREVIEW_AUDIO = "/api/preview-audio";

const SAMPLE_RATES = [
  { value: 0, label: "Как в файле" },
  { value: 16000, label: "16 kHz" },
  { value: 22050, label: "22.05 kHz" },
  { value: 44100, label: "44.1 kHz" },
  { value: 48000, label: "48 kHz" },
];

export default function AudioSettingsModal({
  open,
  onClose,
  audioOptions,
  setAudioField,
  onSave,
  onReset,
  loading,
  audioFile,
  audioFileName,
}) {
  const { previewData, previewLoading, previewError, originalUrl } = usePrepPreview({
    open,
    mediaFile: audioFile,
    mediaFieldName: "audio",
    previewEndpoint: API_PREVIEW_AUDIO,
    options: audioOptions,
    appendOptions: appendAudioOptionsToFormData,
  });

  const prepOff = loading || !audioOptions.prepEnabled;

  return (
    <PrepEditorShell
      open={open}
      titleId="audio-editor-title"
      title="Аудио"
      fileName={audioFileName}
      onClose={onClose}
      onSave={onSave}
      onReset={onReset}
      loading={loading}
      previewLoading={previewLoading}
      preview={
        <LiveComparePreview
          kind="audio"
          loading={previewLoading}
          error={previewError}
          originalUrl={originalUrl}
          originalName={audioFileName}
          data={previewData}
        />
      }
      settings={
        <>
          <EditorSection>
            <label className="editor-toggle">
              <input
                type="checkbox"
                checked={audioOptions.prepEnabled}
                disabled={loading}
                onChange={(e) => setAudioField("prepEnabled", e.target.checked)}
              />
              <span className="editor-toggle__label">Подготовка перед генерацией</span>
            </label>
          </EditorSection>

          <EditorSection
            title="Скорость и синхрон"
            hint="Меньше 100% — замедление речи. Задержка сдвигает старт."
            muted={prepOff}
          >
            <label className="field field--compact">
              <span className="field__label">
                Скорость {Math.round(audioOptions.playbackSpeed * 100)}%
              </span>
              <input
                className="field__range"
                type="range"
                min="0.5"
                max="1.5"
                step="0.05"
                value={audioOptions.playbackSpeed}
                disabled={prepOff}
                onChange={(e) =>
                  setAudioField("playbackSpeed", Number(e.target.value))
                }
              />
            </label>
            <label className="field field--compact">
              <span className="field__label">Задержка {audioOptions.delayMs} мс</span>
              <input
                className="field__range"
                type="range"
                min="0"
                max="3000"
                step="50"
                value={audioOptions.delayMs}
                disabled={prepOff}
                onChange={(e) => setAudioField("delayMs", Number(e.target.value))}
              />
            </label>
          </EditorSection>

          <EditorSection title="Громкость" muted={prepOff}>
            <label className="field field--compact">
              <span className="field__label">
                Усиление {audioOptions.gainDb > 0 ? "+" : ""}
                {audioOptions.gainDb.toFixed(1)} dB
              </span>
              <input
                className="field__range"
                type="range"
                min="-12"
                max="12"
                step="0.5"
                value={audioOptions.gainDb}
                disabled={prepOff}
                onChange={(e) => setAudioField("gainDb", Number(e.target.value))}
              />
            </label>
            <label className="field__checkbox">
              <input
                type="checkbox"
                checked={audioOptions.normalizePeak}
                disabled={prepOff}
                onChange={(e) => setAudioField("normalizePeak", e.target.checked)}
              />
              Нормализовать пик до −1 dB
            </label>
          </EditorSection>

          <EditorSection title="Тишина" muted={prepOff}>
            <label className="field__checkbox">
              <input
                type="checkbox"
                checked={audioOptions.trimSilence}
                disabled={prepOff}
                onChange={(e) => setAudioField("trimSilence", e.target.checked)}
              />
              Обрезать тишину по краям
            </label>
            <label className="field field--compact">
              <span className="field__label">
                Порог {audioOptions.trimThresholdDb} dB
              </span>
              <input
                className="field__range"
                type="range"
                min="-60"
                max="-20"
                step="1"
                value={audioOptions.trimThresholdDb}
                disabled={prepOff || !audioOptions.trimSilence}
                onChange={(e) =>
                  setAudioField("trimThresholdDb", Number(e.target.value))
                }
              />
            </label>
          </EditorSection>

          <EditorSection title="Формат" hint="Для генерации используется WAV." muted={prepOff}>
            <label className="field field--compact">
              <span className="field__label">Макс. длительность (с)</span>
              <input
                className="field__input"
                type="number"
                min="0"
                max="600"
                step="1"
                value={audioOptions.maxDurationSec}
                disabled={prepOff}
                onChange={(e) =>
                  setAudioField("maxDurationSec", Number(e.target.value))
                }
              />
            </label>
            <label className="field field--compact">
              <span className="field__label">Частота</span>
              <select
                className="field__input"
                value={audioOptions.sampleRateHz}
                disabled={prepOff}
                onChange={(e) =>
                  setAudioField("sampleRateHz", Number(e.target.value))
                }
              >
                {SAMPLE_RATES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field__checkbox">
              <input
                type="checkbox"
                checked={audioOptions.forceMono}
                disabled={prepOff}
                onChange={(e) => setAudioField("forceMono", e.target.checked)}
              />
              Моно
            </label>
          </EditorSection>
        </>
      }
    />
  );
}
