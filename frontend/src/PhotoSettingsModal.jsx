import EditorSection from "./EditorSection.jsx";
import LiveComparePreview from "./LiveComparePreview.jsx";
import PrepEditorShell from "./PrepEditorShell.jsx";
import { appendPhotoOptionsToFormData } from "./photoConfig.js";
import { usePrepPreview } from "./usePrepPreview.js";

const API_PREVIEW_PHOTO = "/api/preview-photo";

export default function PhotoSettingsModal({
  open,
  onClose,
  photoOptions,
  setPhotoField,
  onSave,
  onReset,
  loading,
  photoFile,
  photoFileName,
}) {
  const { previewData, previewLoading, previewError, originalUrl } = usePrepPreview({
    open,
    mediaFile: photoFile,
    mediaFieldName: "photo",
    previewEndpoint: API_PREVIEW_PHOTO,
    options: photoOptions,
    appendOptions: appendPhotoOptionsToFormData,
  });

  const prepOff = loading || !photoOptions.prepEnabled;
  const faceOff = prepOff || !photoOptions.faceCheckEnabled;

  return (
    <PrepEditorShell
      open={open}
      titleId="photo-editor-title"
      title="Фото"
      fileName={photoFileName}
      onClose={onClose}
      onSave={onSave}
      onReset={onReset}
      loading={loading}
      previewLoading={previewLoading}
      preview={
        <LiveComparePreview
          kind="photo"
          loading={previewLoading}
          error={previewError}
          originalUrl={originalUrl}
          originalName={photoFileName}
          data={previewData}
        />
      }
      settings={
        <>
          <EditorSection>
            <label className="editor-toggle">
              <input
                type="checkbox"
                checked={photoOptions.prepEnabled}
                disabled={loading}
                onChange={(e) => setPhotoField("prepEnabled", e.target.checked)}
              />
              <span className="editor-toggle__label">Подготовка перед генерацией</span>
            </label>
          </EditorSection>

          <EditorSection title="Лицо" muted={prepOff}>
            <label className="field__checkbox">
              <input
                type="checkbox"
                checked={photoOptions.faceCheckEnabled}
                disabled={prepOff}
                onChange={(e) => setPhotoField("faceCheckEnabled", e.target.checked)}
              />
              Проверять лицо
            </label>
            <div
              className={
                faceOff && !prepOff ? "editor-section__sub editor-section__sub--inactive" : "editor-section__sub"
              }
            >
              <label className="field__checkbox">
                <input
                  type="checkbox"
                  checked={photoOptions.faceRequireSingle}
                  disabled={faceOff}
                  onChange={(e) =>
                    setPhotoField("faceRequireSingle", e.target.checked)
                  }
                />
                Только одно лицо
              </label>
              <label className="field__checkbox">
                <input
                  type="checkbox"
                  checked={photoOptions.faceAutoCrop}
                  disabled={faceOff}
                  onChange={(e) => setPhotoField("faceAutoCrop", e.target.checked)}
                />
                Обрезка по лицу (рот в кадре)
              </label>
              <label className="field__checkbox">
                <input
                  type="checkbox"
                  checked={photoOptions.faceAlignEnabled}
                  disabled={faceOff}
                  onChange={(e) =>
                    setPhotoField("faceAlignEnabled", e.target.checked)
                  }
                />
                Выровнять по глазам (face alignment)
              </label>
              <label className="field field--compact">
                <span className="field__label">
                  Мин. доля лица ({Math.round(photoOptions.minFaceSizeRatio * 100)}%)
                </span>
                <input
                  className="field__range"
                  type="range"
                  min="0.03"
                  max="0.35"
                  step="0.01"
                  value={photoOptions.minFaceSizeRatio}
                  disabled={faceOff}
                  onChange={(e) =>
                    setPhotoField("minFaceSizeRatio", Number(e.target.value))
                  }
                />
              </label>
            </div>
          </EditorSection>

          <EditorSection title="Картинка" muted={prepOff}>
            <label className="field field--compact">
              <span className="field__label">
                Яркость {photoOptions.brightness.toFixed(2)}
              </span>
              <input
                className="field__range"
                type="range"
                min="0.5"
                max="2"
                step="0.05"
                value={photoOptions.brightness}
                disabled={prepOff}
                onChange={(e) => setPhotoField("brightness", Number(e.target.value))}
              />
            </label>
            <label className="field field--compact">
              <span className="field__label">
                Контраст {photoOptions.contrast.toFixed(2)}
              </span>
              <input
                className="field__range"
                type="range"
                min="0.5"
                max="2"
                step="0.05"
                value={photoOptions.contrast}
                disabled={prepOff}
                onChange={(e) => setPhotoField("contrast", Number(e.target.value))}
              />
            </label>
            <label className="field field--compact">
              <span className="field__label">
                Резкость {photoOptions.sharpness.toFixed(2)}
              </span>
              <input
                className="field__range"
                type="range"
                min="0.5"
                max="2.5"
                step="0.05"
                value={photoOptions.sharpness}
                disabled={prepOff}
                onChange={(e) => setPhotoField("sharpness", Number(e.target.value))}
              />
            </label>
          </EditorSection>

          <EditorSection title="Экспорт" muted={prepOff}>
            <label className="field field--compact">
              <span className="field__label">Макс. сторона (px)</span>
              <input
                className="field__input"
                type="number"
                min="512"
                max="4096"
                step="64"
                value={photoOptions.maxEdge}
                disabled={prepOff}
                onChange={(e) => setPhotoField("maxEdge", Number(e.target.value))}
              />
            </label>
            <label className="field field--compact">
              <span className="field__label">JPEG {photoOptions.jpegQuality}</span>
              <input
                className="field__range"
                type="range"
                min="60"
                max="100"
                step="1"
                value={photoOptions.jpegQuality}
                disabled={prepOff}
                onChange={(e) => setPhotoField("jpegQuality", Number(e.target.value))}
              />
            </label>
          </EditorSection>
        </>
      }
    />
  );
}
