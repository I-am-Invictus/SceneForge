import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Asset, AssetKind, Folder } from '../types/assets'
import * as assetsApi from '../services/assets'
import { AssetCard } from './AssetCard'
import { FolderTree } from './FolderTree'
import { NewAssetDialog } from './NewAssetDialog'

interface LibraryPageProps {
  kind: AssetKind
  title: string
}

export function LibraryPage({ kind, title }: LibraryPageProps) {
  const navigate = useNavigate()
  const [folders, setFolders] = useState<Folder[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedFolder, setSelectedFolder] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadFolders = useCallback(() => {
    assetsApi.listFolders(kind).then(setFolders).catch(() => {})
  }, [kind])

  const loadAssets = useCallback(() => {
    setLoading(true)
    assetsApi
      .listAssets(kind, { q: query || undefined, folder_id: selectedFolder })
      .then((result) => {
        setAssets(result)
        setLoading(false)
      })
      .catch((err) => {
        alert(err.message)
        setLoading(false)
      })
  }, [kind, query, selectedFolder])

  useEffect(() => {
    loadFolders()
  }, [loadFolders])

  useEffect(() => {
    const handle = setTimeout(loadAssets, query ? 200 : 0)
    return () => clearTimeout(handle)
  }, [loadAssets, query])

  const handleOpen = (asset: Asset) => {
    const base = kind === 'character' ? '/characters' : '/scenes'
    navigate(`${base}/${asset.id}`)
  }

  return (
    <div className="page library-page">
      <header className="page-header library-header">
        <h1>{title}</h1>
        <div className="library-toolbar">
          <input
            type="search"
            className="search-input"
            placeholder={`Search ${title.toLowerCase()}…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn" onClick={() => setShowNew(true)}>
            {kind === 'character' ? '+ New Character' : '+ New Scene'}
          </button>
        </div>
      </header>

      <div className="library-layout">
        <aside className="library-sidebar">
          <FolderTree
            kind={kind}
            folders={folders}
            selectedId={selectedFolder}
            onSelect={setSelectedFolder}
            onFoldersChanged={loadFolders}
          />
        </aside>
        <div className="library-content">
          {loading ? (
            <p className="empty-note">Loading…</p>
          ) : assets.length === 0 ? (
            <p className="empty-note">
              Nothing here yet.{' '}
              {kind === 'character'
                ? 'Create a character with one or more reference images.'
                : 'Add scene reference images.'}
            </p>
          ) : (
            <div className="asset-grid">
              {assets.map((asset) => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  onOpen={handleOpen}
                  onStarred={(updated) =>
                    setAssets((prev) =>
                      prev.map((a) => (a.id === updated.id ? updated : a)),
                    )
                  }
                  onUpdated={(updated) =>
                    setAssets((prev) =>
                      prev.map((a) => (a.id === updated.id ? updated : a)),
                    )
                  }
                  onDeleted={(assetId) =>
                    setAssets((prev) => prev.filter((a) => a.id !== assetId))
                  }
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {showNew && (
        <NewAssetDialog
          kind={kind}
          folders={folders}
          onCreated={loadAssets}
          onClose={() => setShowNew(false)}
        />
      )}
    </div>
  )
}
