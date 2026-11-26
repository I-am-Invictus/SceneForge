import type { Asset } from '../types/assets'
import { patchAsset } from '../services/assets'

interface AssetCardProps {
  asset: Asset
  onOpen: (asset: Asset) => void
  onStarred: (asset: Asset) => void
}

export function AssetCard({ asset, onOpen, onStarred }: AssetCardProps) {
  const toggleStar = (e: React.MouseEvent) => {
    e.stopPropagation()
    patchAsset(asset.kind as 'character' | 'scene', asset.id, {
      is_favorite: !asset.is_favorite,
    })
      .then(onStarred)
      .catch((err) => alert(err.message))
  }

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
        <span className="asset-card-meta">
          {asset.reference_count} {asset.reference_count === 1 ? 'image' : 'images'}
        </span>
      </div>
    </div>
  )
}
