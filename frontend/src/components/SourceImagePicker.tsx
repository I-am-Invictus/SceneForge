import { useEffect, useRef, useState } from 'react'
import { Dialog } from './Dialog'
import {
  addReferences,
  createAssets,
  deleteFile,
  listAssets,
  setDefaultFile,
} from '../services/assets'
import type { Asset, AssetFile, AssetKind } from '../types/assets'

interface SourceImagePickerProps {
  onClose: () => void
  onSelect: (asset: Asset, file: AssetFile) => void
  /** The library shown for selection (and the upload destination):
   *  'character' when editing a character, 'scene' when editing a scene. */
  kind: AssetKind
  /** Called after an upload so the parent can refresh its asset lists. */
  onAssetsChanged: () => void
}

const KIND_LABEL: Record<AssetKind, { plural: string; noun: string }> = {
  character: { plural: 'Characters', noun: 'character' },
  scene: { plural: 'Scenes', noun: 'scene' },
}

export function SourceImagePicker({
  onClose,
  onSelect,
  kind,
  onAssetsChanged,
}: SourceImagePickerProps) {
  const [assets, setAssets] = useState<Asset[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const addRefInput = useRef<HTMLInputElement>(null)

  const labels = KIND_LABEL[kind]

  useEffect(() => {
    let cancelled = false
    setAssets(null)
    setError(null)
    setExpanded(null)
    listAssets(kind)
      .then((list) => {
        if (!cancelled) setAssets(list)
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [kind])

  const expandedAsset = assets?.find((a) => a.id === expanded) ?? null

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    try {
      const name =
        files[0].name.replace(/\.[^.]+$/, '') ||
        (kind === 'character' ? 'Character' : 'Scene')
      const created = await createAssets(kind, [files[0]], name)
      onAssetsChanged()
      const asset = created[0]
      const file = asset.files.find((f) => f.is_default) ?? asset.files[0]
      onSelect(asset, file)
    } catch (e) {
      setUploadError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  // Reference management for the expanded asset — the same add / set-default /
  // remove behavior as the asset detail page, so it can be done here without
  // leaving the workflow.
  function replaceAsset(updated: Asset) {
    setAssets((prev) =>
      prev ? prev.map((a) => (a.id === updated.id ? updated : a)) : prev,
    )
    onAssetsChanged()
  }

  async function handleSetDefault(fileId: number) {
    if (!expandedAsset) return
    setUploadError(null)
    try {
      replaceAsset(await setDefaultFile(kind, expandedAsset.id, fileId))
    } catch (e) {
      setUploadError((e as Error).message)
    }
  }

  async function handleRemoveFile(fileId: number) {
    if (!expandedAsset) return
    setUploadError(null)
    try {
      replaceAsset(await deleteFile(kind, expandedAsset.id, fileId))
    } catch (e) {
      setUploadError((e as Error).message)
    }
  }

  async function handleAddReferences(files: FileList) {
    if (!expandedAsset) return
    setUploading(true)
    setUploadError(null)
    try {
      replaceAsset(await addReferences(kind, expandedAsset.id, files))
    } catch (e) {
      setUploadError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog title="Select source image" onClose={onClose} wide>
      <label className="file-drop">
        {uploading
          ? 'Uploading…'
          : `Upload an image to the ${labels.plural} library`}
        <input
          type="file"
          accept="image/*"
          hidden
          disabled={uploading}
          onChange={(e) => {
            void handleUpload(e.target.files)
            e.target.value = ''
          }}
        />
      </label>
      {uploadError && <p className="form-error">{uploadError}</p>}

      <div className="picker-divider">or choose from {labels.plural}</div>

      {error && <p className="form-error">{error}</p>}
      {!assets && !error && (
        <div className="empty-note">Loading {labels.plural.toLowerCase()}…</div>
      )}
      {assets && assets.length === 0 && !error && (
        <div className="empty-note">
          No {labels.plural.toLowerCase()} yet — upload an image above to
          create one.
        </div>
      )}
      {assets && assets.length > 0 && (
        <div className="picker-grid">
          {assets.map((asset) => (
            <button
              key={asset.id}
              type="button"
              className={`picker-card ${expanded === asset.id ? 'active' : ''}`}
              onClick={() =>
                setExpanded(expanded === asset.id ? null : asset.id)
              }
            >
              <div className="picker-card-thumb">
                {asset.thumbnail_url && (
                  <img src={asset.thumbnail_url} alt="" loading="lazy" />
                )}
              </div>
              <span className="picker-card-name">{asset.name}</span>
              <span className="picker-card-meta">
                {asset.files.length} image{asset.files.length === 1 ? '' : 's'}
              </span>
            </button>
          ))}
        </div>
      )}

      {expandedAsset && (
        <div className="picker-files">
          {expandedAsset.files.map((file) => (
            <div
              key={file.id}
              className="picker-file"
              role="button"
              tabIndex={0}
              onClick={() => onSelect(expandedAsset, file)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onSelect(expandedAsset, file)
              }}
              title={file.display_name}
            >
              <img src={file.thumbnail_url} alt="" loading="lazy" />
              <span className="picker-file-meta">
                {file.width}×{file.height}
              </span>
              {file.is_default && (
                <span className="picker-file-default">Default</span>
              )}
              <span className="picker-file-actions">
                {!file.is_default && (
                  <button
                    type="button"
                    className="icon-btn"
                    title="Set as default"
                    onClick={(e) => {
                      e.stopPropagation()
                      void handleSetDefault(file.id)
                    }}
                  >
                    ★
                  </button>
                )}
                <button
                  type="button"
                  className="icon-btn"
                  title="Remove image"
                  onClick={(e) => {
                    e.stopPropagation()
                    void handleRemoveFile(file.id)
                  }}
                >
                  ✕
                </button>
              </span>
            </div>
          ))}
          <button
            type="button"
            className="picker-file-add"
            onClick={() => addRefInput.current?.click()}
          >
            + Add reference
            <input
              ref={addRefInput}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              multiple
              hidden
              disabled={uploading}
              onChange={(e) => {
                if (e.target.files?.length) handleAddReferences(e.target.files)
                e.target.value = ''
              }}
            />
          </button>
        </div>
      )}
    </Dialog>
  )
}
