import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { Asset, AssetKind, Folder } from '../types/assets'
import * as assetsApi from '../services/assets'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { MoveDialog } from '../components/MoveDialog'
import { RenameDialog } from '../components/RenameDialog'

export function AssetDetailPage({ kind }: { kind: AssetKind }) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const assetId = Number(id)
  const [asset, setAsset] = useState<Asset | null>(null)
  const [folders, setFolders] = useState<Folder[]>([])
  const [notFound, setNotFound] = useState(false)
  const [dialog, setDialog] = useState<'rename' | 'move' | 'delete' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const addRefInput = useRef<HTMLInputElement>(null)

  const basePath = kind === 'character' ? '/characters' : '/scenes'

  const load = useCallback(() => {
    assetsApi
      .getAsset(kind, assetId)
      .then(setAsset)
      .catch(() => setNotFound(true))
  }, [kind, assetId])

  useEffect(() => {
    load()
    assetsApi.listFolders(kind).then(setFolders).catch(() => {})
  }, [load, kind])

  if (notFound) {
    return (
      <div className="page">
        <p className="empty-note">Asset not found.</p>
      </div>
    )
  }

  if (!asset) {
    return (
      <div className="page">
        <p className="empty-note">Loading…</p>
      </div>
    )
  }

  const isCharacter = kind === 'character'

  const addReferences = async (files: FileList) => {
    try {
      setAsset(await assetsApi.addReferences(kind, assetId, files))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="page">
      <header className="page-header detail-header">
        <button
          className="btn secondary back-btn"
          onClick={() => navigate(basePath)}
        >
          ← {isCharacter ? 'Characters' : 'Scenes'}
        </button>
        <h1>{asset.name}</h1>
        <div className="detail-actions">
          <button
            className={`star-btn inline ${asset.is_favorite ? 'active' : ''}`}
            onClick={() =>
              assetsApi
                .patchAsset(kind, assetId, { is_favorite: !asset.is_favorite })
                .then(setAsset)
            }
          >
            {asset.is_favorite ? '★ Starred' : '☆ Star'}
          </button>
          <button className="btn secondary" onClick={() => setDialog('rename')}>
            Rename
          </button>
          <button className="btn secondary" onClick={() => setDialog('move')}>
            Move
          </button>
          <button className="btn danger" onClick={() => setDialog('delete')}>
            Delete
          </button>
        </div>
      </header>

      {error && <p className="form-error">{error}</p>}

      <div className="references-grid">
        {asset.files.map((file) => (
          <div className="reference-card" key={file.id}>
            <div className="reference-thumb">
              <a href={file.original_url}>
                <img src={file.thumbnail_url} alt={file.display_name} loading="lazy" />
              </a>
              {file.is_default && <span className="default-badge">Default</span>}
            </div>
            <div className="reference-footer">
              <span className="reference-name" title={file.display_name}>
                {file.display_name}
              </span>
              <span className="reference-meta">
                {file.width}×{file.height}
              </span>
              {isCharacter && (
                <span className="reference-actions">
                  {!file.is_default && (
                    <button
                      className="icon-btn"
                      title="Set as default"
                      onClick={() =>
                        assetsApi
                          .setDefaultFile(kind, assetId, file.id)
                          .then(setAsset)
                      }
                    >
                      ★
                    </button>
                  )}
                  <button
                    className="icon-btn"
                    title="Remove image"
                    onClick={() =>
                      assetsApi
                        .deleteFile(kind, assetId, file.id)
                        .then(setAsset)
                    }
                  >
                    ✕
                  </button>
                </span>
              )}
            </div>
          </div>
        ))}

        {isCharacter && (
          <button
            className="reference-add"
            onClick={() => addRefInput.current?.click()}
          >
            + Add reference
            <input
              ref={addRefInput}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files?.length) addReferences(e.target.files)
                e.target.value = ''
              }}
            />
          </button>
        )}
      </div>

      {dialog === 'rename' && (
        <RenameDialog
          title={`Rename ${isCharacter ? 'character' : 'scene'}`}
          initialName={asset.name}
          onRename={(name) =>
            assetsApi.patchAsset(kind, assetId, { name }).then(setAsset)
          }
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'move' && (
        <MoveDialog
          title="Move to folder"
          folders={folders}
          initialFolderId={asset.folder_id}
          onMove={(folderId) =>
            assetsApi.moveAsset(kind, assetId, folderId).then(setAsset)
          }
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'delete' && (
        <ConfirmDialog
          title={`Delete ${isCharacter ? 'character' : 'scene'}`}
          message={`Delete "${asset.name}" and its ${asset.reference_count} image(s)? This cannot be undone.`}
          onConfirm={async () => {
            await assetsApi.deleteAsset(kind, assetId)
            navigate(basePath)
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}
