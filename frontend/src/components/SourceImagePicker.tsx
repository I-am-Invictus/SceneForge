import { useEffect, useState } from 'react'
import { Dialog } from './Dialog'
import { createAssets, listAssets } from '../services/assets'
import type { Asset, AssetFile } from '../types/assets'

interface SourceImagePickerProps {
  onClose: () => void
  onSelect: (asset: Asset, file: AssetFile) => void
  /** Called after an upload so the parent can refresh its scene list. */
  onAssetsChanged: () => void
}

export function SourceImagePicker({
  onClose,
  onSelect,
  onAssetsChanged,
}: SourceImagePickerProps) {
  const [assets, setAssets] = useState<Asset[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listAssets('scene')
      .then((list) => {
        if (!cancelled) setAssets(list)
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const expandedAsset = assets?.find((a) => a.id === expanded) ?? null

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    try {
      const name = files[0].name.replace(/\.[^.]+$/, '') || 'Scene'
      const created = await createAssets('scene', [files[0]], name)
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

  return (
    <Dialog title="Select source image" onClose={onClose} wide>
      <label className="file-drop">
        {uploading ? 'Uploading…' : 'Upload an image to the Scenes library'}
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

      <div className="picker-divider">or choose from Scenes</div>

      {error && <p className="form-error">{error}</p>}
      {!assets && !error && <div className="empty-note">Loading scenes…</div>}
      {assets && assets.length === 0 && !error && (
        <div className="empty-note">
          No scenes yet — upload an image above to create one.
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
            <button
              key={file.id}
              type="button"
              className="picker-file"
              onClick={() => onSelect(expandedAsset, file)}
              title={file.display_name}
            >
              <img src={file.thumbnail_url} alt="" loading="lazy" />
              <span className="picker-file-meta">
                {file.width}×{file.height}
              </span>
            </button>
          ))}
        </div>
      )}
    </Dialog>
  )
}
