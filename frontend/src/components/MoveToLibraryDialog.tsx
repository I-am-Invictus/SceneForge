import { useEffect, useState } from 'react'
import { Dialog } from './Dialog'
import { Icon } from './icons'
import { listAssets } from '../services/assets'
import type { Asset, AssetKind } from '../types/assets'

interface MoveToLibraryDialogProps {
  /** File the image as a brand-new asset in the given library (existing behavior). */
  onMove: (folder: AssetKind) => Promise<void>
  /** Attach the image to an existing asset's reference collection. */
  onAddToExisting: (
    kind: AssetKind,
    assetId: number,
    makeDefault: boolean,
  ) => Promise<void>
  onClose: () => void
}

type Mode = 'new' | 'existing'

const CATEGORIES: {
  kind: AssetKind
  label: string
  icon: 'characters' | 'scenes'
}[] = [
  { kind: 'character', label: 'Characters', icon: 'characters' },
  { kind: 'scene', label: 'Scenes', icon: 'scenes' },
]

export function MoveToLibraryDialog({
  onMove,
  onAddToExisting,
  onClose,
}: MoveToLibraryDialogProps) {
  const [mode, setMode] = useState<Mode>('new')
  const [kind, setKind] = useState<AssetKind>('character')
  const [assets, setAssets] = useState<Asset[] | null>(null)
  const [loadingAssets, setLoadingAssets] = useState(false)
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null)
  const [makeDefault, setMakeDefault] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const category = CATEGORIES.find((c) => c.kind === kind)!

  useEffect(() => {
    if (mode !== 'existing') return
    let cancelled = false
    setLoadingAssets(true)
    setAssets(null)
    setError(null)
    listAssets(kind)
      .then((list) => {
        if (!cancelled) setAssets(list)
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
      .finally(() => {
        if (!cancelled) setLoadingAssets(false)
      })
    return () => {
      cancelled = true
    }
  }, [mode, kind])

  async function handleNew(target: AssetKind) {
    setBusy(target)
    setError(null)
    try {
      await onMove(target)
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  async function handleExisting() {
    if (selectedAssetId == null) return
    setBusy('existing')
    setError(null)
    try {
      await onAddToExisting(kind, selectedAssetId, makeDefault)
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  return (
    <Dialog title="Add image to library" onClose={onClose}>
      <p className="dialog-sub">
        The image is preserved and stays in this job&rsquo;s results and in
        generation history. File it as a new asset, or attach it to an existing
        one&rsquo;s references.
      </p>

      <div className="seg" role="tablist" aria-label="Destination type">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'new'}
          className={mode === 'new' ? 'active' : ''}
          disabled={busy !== null}
          onClick={() => setMode('new')}
        >
          New asset
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'existing'}
          className={mode === 'existing' ? 'active' : ''}
          disabled={busy !== null}
          onClick={() => setMode('existing')}
        >
          Existing asset
        </button>
      </div>

      {mode === 'new' ? (
        <div className="move-options">
          {CATEGORIES.map((option) => (
            <button
              key={option.kind}
              type="button"
              className="move-option"
              disabled={busy !== null}
              onClick={() => void handleNew(option.kind)}
            >
              <Icon name={option.icon} size={20} />
              <span>{busy === option.kind ? 'Adding…' : option.label}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="existing-pick">
          <div className="move-options">
            {CATEGORIES.map((option) => (
              <button
                key={option.kind}
                type="button"
                className={`move-option ${kind === option.kind ? 'selected' : ''}`}
                disabled={busy !== null}
                onClick={() => {
                  setKind(option.kind)
                  setSelectedAssetId(null)
                }}
              >
                <Icon name={option.icon} size={20} />
                <span>{option.label}</span>
              </button>
            ))}
          </div>

          {loadingAssets ? (
            <p className="dialog-sub">
              Loading {category.label.toLowerCase()}…
            </p>
          ) : assets && assets.length === 0 ? (
            <p className="dialog-sub">
              No {category.label.toLowerCase()} yet. Choose &ldquo;New
              asset&rdquo; to create one.
            </p>
          ) : (
            <>
              <div className="existing-pick-list">
                {assets?.map((asset) => {
                  const thumb = asset.thumbnail_url ?? asset.files[0]?.thumbnail_url
                  return (
                    <button
                      key={asset.id}
                      type="button"
                      className={`existing-pick-row ${
                        selectedAssetId === asset.id ? 'active' : ''
                      }`}
                      disabled={busy !== null}
                      onClick={() => {
                        setSelectedAssetId(asset.id)
                        setMakeDefault(false)
                      }}
                    >
                      {thumb && <img src={thumb} alt="" />}
                      <span className="existing-pick-name">{asset.name}</span>
                      <span className="existing-pick-count">
                        {asset.reference_count}{' '}
                        {asset.reference_count === 1 ? 'reference' : 'references'}
                      </span>
                    </button>
                  )
                })}
              </div>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={makeDefault}
                  disabled={selectedAssetId == null || busy !== null}
                  onChange={(e) => setMakeDefault(e.target.checked)}
                />
                Set as the default reference
              </label>
              <button
                type="button"
                className="btn"
                disabled={busy !== null || selectedAssetId == null}
                onClick={() => void handleExisting()}
              >
                {busy === 'existing' ? 'Adding…' : 'Add to selected asset'}
              </button>
            </>
          )}
        </div>
      )}

      {error && <p className="form-error">{error}</p>}
    </Dialog>
  )
}
