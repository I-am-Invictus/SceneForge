import { useEffect } from 'react'
import { Icon } from './icons'
import {
  ImageComparison,
  type CompareImage,
} from './ImageComparison'
import type { GalleryImage } from '../types/galleries'

interface GalleryImageViewerProps {
  images: GalleryImage[]
  index: number
  onIndex: (i: number) => void
  onClose: () => void
  onAddToLibrary: (clientId: string, outputId: number) => void
  onAddToGallery: (clientId: string, outputId: number) => void
  onRemoveFromGallery: (outputId: number) => void
  onDelete: (clientId: string, outputId: number) => void
}

/**
 * Focused viewer for a single gallery image. It reuses {@link ImageComparison}
 * so the before/after comparison behaves exactly like the job result viewer.
 * One instance stays mounted while navigation changes `index`, which is what
 * keeps the user's selected comparison mode across images.
 */
export function GalleryImageViewer({
  images,
  index,
  onIndex,
  onClose,
  onAddToLibrary,
  onAddToGallery,
  onRemoveFromGallery,
  onDelete,
}: GalleryImageViewerProps) {
  const image = images[index]
  const canPrev = index > 0
  const canNext = index < images.length - 1

  const goPrev = () => {
    if (canPrev) onIndex(index - 1)
  }
  const goNext = () => {
    if (canNext) onIndex(index + 1)
  }

  // Keyboard navigation. Ignore keys targeted at the comparison slider grip or
  // any text field so we never fight their own arrow-key handling.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null
      if (
        t &&
        (t.closest('[role="slider"]') ||
          t.tagName === 'INPUT' ||
          t.tagName === 'TEXTAREA')
      ) {
        return
      }
      if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === 'ArrowRight') goNext()
      else if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, images.length])

  if (!image) return null

  const generated: CompareImage = {
    src: image.original_url,
    alt: image.comfyui_filename,
    width: image.width ?? undefined,
    height: image.height ?? undefined,
  }
  const original: CompareImage | null = image.original
    ? {
        src: image.original.url,
        width: image.original.width ?? undefined,
        height: image.original.height ?? undefined,
        alt: image.original.alt,
      }
    : null

  return (
    <div className="gallery-viewer-backdrop" onClick={onClose}>
      <div
        className="gallery-viewer"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="gallery-viewer-head">
          <span className="gallery-viewer-title">
            {image.prompt || image.comfyui_filename}
          </span>
          <span className="gallery-viewer-count">
            {index + 1} / {images.length}
          </span>
          <button
            className="icon-btn"
            onClick={onClose}
            aria-label="Close viewer"
          >
            ×
          </button>
        </div>

        <ImageComparison
          original={original}
          generated={generated}
          resultKey={String(image.output_id)}
          onPrev={goPrev}
          onNext={goNext}
          canPrev={canPrev}
          canNext={canNext}
        />

        <div className="gallery-viewer-actions">
          <button
            type="button"
            className="btn secondary"
            onClick={() => onAddToLibrary(image.job_client_id, image.output_id)}
          >
            <Icon name="moveToLibrary" size={14} />
            Add to library
          </button>
          <button
            type="button"
            className="btn secondary"
            onClick={() => onAddToGallery(image.job_client_id, image.output_id)}
          >
            <Icon name="galleries" size={14} />
            Add to gallery
          </button>
          <button
            type="button"
            className="btn secondary"
            onClick={() => onRemoveFromGallery(image.output_id)}
          >
            <Icon name="close" size={14} />
            Remove from gallery
          </button>
          <button
            type="button"
            className="btn danger"
            onClick={() => onDelete(image.job_client_id, image.output_id)}
          >
            <Icon name="trash" size={14} />
            Delete image
          </button>
        </div>

        {image.prompt && <p className="gallery-viewer-prompt">{image.prompt}</p>}

        <div className="gallery-viewer-filmstrip">
          {images.map((img, i) => (
            <button
              key={img.output_id}
              type="button"
              className={`filmstrip-thumb ${i === index ? 'active' : ''}`}
              onClick={() => onIndex(i)}
              aria-label={`Show image ${i + 1} of ${images.length}`}
            >
              <img src={img.thumbnail_url} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
