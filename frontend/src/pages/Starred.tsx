import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Asset } from '../types/assets'
import { listAssets } from '../services/assets'
import { AssetCard } from '../components/AssetCard'

export function Starred() {
  const navigate = useNavigate()
  const [characters, setCharacters] = useState<Asset[]>([])
  const [scenes, setScenes] = useState<Asset[]>([])

  useEffect(() => {
    listAssets('character', { favorite: true }).then(setCharacters).catch(() => {})
    listAssets('scene', { favorite: true }).then(setScenes).catch(() => {})
  }, [])

  const open = (asset: Asset) => {
    const base = asset.kind === 'character' ? '/characters' : '/scenes'
    navigate(`${base}/${asset.id}`)
  }

  const renderSection = (title: string, items: Asset[], kind: 'character' | 'scene') => (
    <section>
      <h2 className="starred-section-title">{title}</h2>
      {items.length === 0 ? (
        <p className="empty-note">No starred {title.toLowerCase()} yet.</p>
      ) : (
        <div className="asset-grid">
          {items.map((asset) => (
            <AssetCard
              key={asset.id}
              asset={asset}
              onOpen={open}
              onStarred={(updated) =>
                kind === 'character'
                  ? setCharacters((prev) =>
                      prev.filter((a) => a.id !== updated.id),
                    )
                  : setScenes((prev) => prev.filter((a) => a.id !== updated.id))
              }
            />
          ))}
        </div>
      )}
    </section>
  )

  return (
    <div className="page">
      <header className="page-header">
        <h1>Starred Assets</h1>
      </header>
      {renderSection('Characters', characters, 'character')}
      {renderSection('Scenes', scenes, 'scene')}
    </div>
  )
}
