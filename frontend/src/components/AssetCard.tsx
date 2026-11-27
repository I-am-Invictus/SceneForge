import { useState } from 'react'
import type { Asset, AssetKind } from '../types/assets'
import * as assetsApi from '../services/assets'
import { ConfirmDialog } from './ConfirmDialog'
import { EditAssetDialog } from './EditAssetDialog'

interface AssetCardProps {
  asset: Asset
  onOpen: (asset: Asset) => void
  onStarred: (asset: Asset) => void
  onUpdated: (asset: Asset) => void
  onDeleted: (assetId: number) => void
}

export function AssetCard({
  asset,
  onOpen,
  onStarred,
  onUpdated,
  onDeleted,
}: AssetCardProps) {
  const [dialog, setDialog] = useState<'edit' | 'delete' | null>(null)
  const kind = asset.kind as AssetKind
  const noun = kind === 'character' ? 'character' : 'scene'

  const toggleStar = (e: React.MouseEvent) => {
    e.stopPropagation()
    assetsApi
      .patchAsset(kind, asset.id, { is_favorite: !asset.is_favorite })
      .then(onStarred)
      .catch((err) => alert(err.message))
  }

  const stop = (e: React.MouseEvent) => e.stopPropagation()

  return (
    <div className="asset-card" onClick={() => onOpen(asset)}>
      <div className="asset-thumb">
        {asset.thumbnail_url ? (
          <img
            src={asset.thumbnail_url}
            alt={asset.name}
            loading="lazy"
          />
        ) : (
          <div className="asset-thumb-empty">No image</div>
        )}
        <button
          className={`star-btn ${asset.is_favorite ? 'active' : ''}`}
          onClick={toggleStar}
          title={asset.is_favorite ? 'Unstar' : 'Star'}
        >
          {asset.is_favorite ? '★' : '☆'}
        </button>
      </div>
      <div className="asset-card-footer">
        <span className="asset-card-name">{asset.name}</span>
        <span className="asset-card-side">
          <span className="asset-card-meta">
            {asset.reference_count}{' '}
            {asset.reference_count === 1 ? 'image' : 'images'}
          </span>
          <button
            className="icon-btn"
            title={`Edit ${noun} details`}
            onClick={(e) => {
              stop(e)
              setDialog('edit')
            }}
          >
            ✎
          </button>
          <button
            className="icon-btn"
            title={`Delete ${noun}`}
            onClick={(e) => {
              stop(e)
              setDialog('delete')
            }}
          >
            ✕
          </button>
        </span>
      </div>

      {dialog === 'edit' && (
        <EditAssetDialog
          title={`Edit ${noun}`}
          initialName={asset.name}
          initialDescription={asset.description}
          initialTags={asset.tags}
          onSave={(name, description, tags) =>
            assetsApi
              .patchAsset(kind, asset.id, { name, description, tags })
              .then(onUpdated)
          }
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'delete' && (
        <ConfirmDialog
          title={`Delete ${noun}`}
          message={`Delete "${asset.name}" and its ${asset.reference_count} image(s) from the ${
            kind === 'character' ? 'Characters' : 'Scenes'
          } library? Images that are still used by past jobs are kept. This cannot be undone.`}
          onConfirm={async () => {
            await assetsApi.deleteAsset(kind, asset.id)
            onDeleted(asset.id)
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}
