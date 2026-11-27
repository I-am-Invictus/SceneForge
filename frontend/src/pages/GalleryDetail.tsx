import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Icon } from '../components/icons'
import { AddToGalleryDialog } from '../components/AddToGalleryDialog'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { GalleryImageViewer } from '../components/GalleryImageViewer'
import { MoveToLibraryDialog } from '../components/MoveToLibraryDialog'
import {
  deleteGallery,
  getGallery,
  listGalleryImages,
  removeGalleryImage,
  renameGallery,
} from '../services/galleries'
import { deleteJobOutput, moveJobOutput } from '../services/jobs'
import type { AssetKind } from '../types/assets'
import type { Gallery, GalleryImage } from '../types/galleries'

type ConfirmState =
  | { type: 'delete-image'; clientId: string; outputId: number }
  | { type: 'delete-gallery' }
  | null

export function GalleryDetail() {
  const { id } = useParams<{ id: string }>()
  const galleryId = Number(id)
  const navigate = useNavigate()

  const [gallery, setGallery] = useState<Gallery | null>(null)
  const [images, setImages] = useState<GalleryImage[] | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [viewing, setViewing] = useState<number | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [nameText, setNameText] = useState('')
  const [renamingBusy, setRenamingBusy] = useState(false)

  const [moveTarget, setMoveTarget] = useState<{
    clientId: string
    outputId: number
  } | null>(null)
  const [galleryTarget, setGalleryTarget] = useState<{
    clientId: string
    outputId: number
  } | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState>(null)

  const load = useCallback(() => {
    Promise.all([getGallery(galleryId), listGalleryImages(galleryId)])
      .then(([g, imgs]) => {
        setGallery(g)
        setImages(imgs)
      })
      .catch(() => setNotFound(true))
  }, [galleryId])

  useEffect(() => {
    load()
  }, [load])

  function dropImage(outputId: number) {
    if (!images) return
    const idx = images.findIndex((im) => im.output_id === outputId)
    const next = images.filter((im) => im.output_id !== outputId)
    setImages(next)
    if (viewing !== null) {
      if (next.length === 0) setViewing(null)
      else if (idx >= 0 && idx < viewing) setViewing(viewing - 1)
      else if (idx === viewing) setViewing(Math.min(viewing, next.length - 1))
    }
  }

  async function handleRemoveFromGallery(outputId: number) {
    try {
      await removeGalleryImage(galleryId, outputId)
      dropImage(outputId)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleDeleteConfirmed() {
    if (!confirm) return
    if (confirm.type === 'delete-gallery') {
      await deleteGallery(galleryId)
      navigate('/galleries')
    } else {
      await deleteJobOutput(confirm.clientId, confirm.outputId)
      dropImage(confirm.outputId)
    }
  }

  async function handleRename() {
    const trimmed = nameText.trim()
    if (!trimmed || renamingBusy) return
    setRenamingBusy(true)
    setError(null)
    try {
      const updated = await renameGallery(galleryId, trimmed)
      setGallery(updated)
      setRenaming(false)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRenamingBusy(false)
    }
  }

  if (notFound) {
    return (
      <div className="page">
        <p className="empty-note">Gallery not found.</p>
      </div>
    )
  }
  if (!gallery) {
    return (
      <div className="page">
        <p className="empty-note">Loading…</p>
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header detail-header">
        <button
          className="btn secondary back-btn"
          onClick={() => navigate('/galleries')}
        >
          ← Galleries
        </button>
        <div className="detail-title-wrap">
          {renaming ? (
            <div className="gallery-rename">
              <input
                autoFocus
                value={nameText}
                onChange={(e) => setNameText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleRename()
                  if (e.key === 'Escape') setRenaming(false)
                }}
              />
              <button
                className="btn"
                onClick={() => void handleRename()}
                disabled={renamingBusy || !nameText.trim()}
              >
                {renamingBusy ? 'Saving…' : 'Save'}
              </button>
              <button
                className="btn secondary"
                onClick={() => setRenaming(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <h1>{gallery.name}</h1>
          )}
        </div>
        <div className="detail-actions">
          {!renaming && (
            <button
              className="btn secondary"
              onClick={() => {
                setNameText(gallery.name)
                setRenaming(true)
              }}
            >
              Rename
            </button>
          )}
          <button className="btn danger" onClick={() => setConfirm({ type: 'delete-gallery' })}>
            Delete gallery
          </button>
        </div>
      </header>

      {error && <p className="form-error">{error}</p>}

      {images === null ? (
        <p className="empty-note">Loading images…</p>
      ) : images.length === 0 ? (
        <p className="empty-note">
          This gallery is empty. Add images to it from any job result.
        </p>
      ) : (
        <>
          <p className="gallery-detail-count">
            {images.length} image{images.length === 1 ? '' : 's'}
          </p>
          <div className="gallery-image-grid">
            {images.map((img, i) => (
              <div
                key={img.output_id}
                className="gallery-image"
                role="button"
                tabIndex={0}
                title={img.prompt || img.comfyui_filename}
                onClick={() => setViewing(i)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setViewing(i)
                }}
              >
                <img
                  src={img.thumbnail_url}
                  alt={img.comfyui_filename}
                  loading="lazy"
                />
                <div className="gallery-image-actions">
                  <button
                    type="button"
                    title="Add to library"
                    onClick={(e) => {
                      e.stopPropagation()
                      setMoveTarget({
                        clientId: img.job_client_id,
                        outputId: img.output_id,
                      })
                    }}
                  >
                    <Icon name="moveToLibrary" size={14} />
                  </button>
                  <button
                    type="button"
                    title="Add to gallery"
                    onClick={(e) => {
                      e.stopPropagation()
                      setGalleryTarget({
                        clientId: img.job_client_id,
                        outputId: img.output_id,
                      })
                    }}
                  >
                    <Icon name="galleries" size={14} />
                  </button>
                  <button
                    type="button"
                    title="Remove from this gallery"
                    onClick={(e) => {
                      e.stopPropagation()
                      void handleRemoveFromGallery(img.output_id)
                    }}
                  >
                    <Icon name="close" size={14} />
                  </button>
                  <button
                    type="button"
                    title="Delete image"
                    onClick={(e) => {
                      e.stopPropagation()
                      setConfirm({
                        type: 'delete-image',
                        clientId: img.job_client_id,
                        outputId: img.output_id,
                      })
                    }}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {viewing !== null && images && images.length > 0 && (
        <GalleryImageViewer
          images={images}
          index={Math.min(viewing, images.length - 1)}
          onIndex={setViewing}
          onClose={() => setViewing(null)}
          onAddToLibrary={(clientId, outputId) =>
            setMoveTarget({ clientId, outputId })
          }
          onAddToGallery={(clientId, outputId) =>
            setGalleryTarget({ clientId, outputId })
          }
          onRemoveFromGallery={(outputId) => void handleRemoveFromGallery(outputId)}
          onDelete={(clientId, outputId) =>
            setConfirm({ type: 'delete-image', clientId, outputId })
          }
        />
      )}

      {moveTarget && (
        <MoveToLibraryDialog
          onMove={async (folder: AssetKind) => {
            await moveJobOutput(
              moveTarget.clientId,
              moveTarget.outputId,
              folder,
            )
          }}
          onClose={() => setMoveTarget(null)}
        />
      )}

      {galleryTarget && (
        <AddToGalleryDialog
          outputId={galleryTarget.outputId}
          onClose={() => {
            setGalleryTarget(null)
            load()
          }}
        />
      )}

      {confirm && (
        <ConfirmDialog
          title={
            confirm.type === 'delete-gallery'
              ? 'Delete this gallery?'
              : 'Delete this image?'
          }
          message={
            confirm.type === 'delete-gallery'
              ? `Delete "${gallery.name}"? The images it contains are not deleted — they remain in their jobs and any other galleries.`
              : 'This permanently removes the image and its thumbnail from all jobs and galleries. This cannot be undone.'
          }
          confirmLabel={confirm.type === 'delete-gallery' ? 'Delete gallery' : 'Delete image'}
          onConfirm={handleDeleteConfirmed}
          onClose={() => setConfirm(null)}
        />
      )}
    </div>
  )
}
