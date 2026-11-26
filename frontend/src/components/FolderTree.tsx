import { useState } from 'react'
import type { AssetKind, Folder } from '../types/assets'
import { createFolder, deleteFolder, renameFolder } from '../services/assets'

interface FolderTreeProps {
  kind: AssetKind
  folders: Folder[]
  selectedId: number | null
  onSelect: (folderId: number | null) => void
  onFoldersChanged: () => void
}

export function FolderTree({
  kind,
  folders,
  selectedId,
  onSelect,
  onFoldersChanged,
}: FolderTreeProps) {
  const [creatingUnder, setCreatingUnder] = useState<number | null | 'root'>(null)
  const [renaming, setRenaming] = useState<Folder | null>(null)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const childrenOf = (parentId: number | null): Folder[] =>
    folders
      .filter((f) => f.parent_id === parentId)
      .sort((a, b) => a.name.localeCompare(b.name))

  const commitCreate = async () => {
    if (!newName.trim()) {
      setCreatingUnder(null)
      return
    }
    try {
      await createFolder(
        kind,
        newName,
        creatingUnder === 'root' ? null : creatingUnder,
      )
      setCreatingUnder(null)
      setNewName('')
      onFoldersChanged()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const commitRename = async () => {
    if (!renaming || !newName.trim()) return
    try {
      await renameFolder(kind, renaming.id, newName)
      setRenaming(null)
      onFoldersChanged()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const renderRow = (folder: Folder, depth: number) => {
    const isSelected = selectedId === folder.id
    return (
      <div key={folder.id} className="folder-row-wrap">
        <div
          className={`folder-row ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: 10 + depth * 14 }}
          onClick={() => {
            onSelect(folder.id)
            setCreatingUnder(null)
          }}
        >
          <span className="folder-name">{folder.name}</span>
          <span className="folder-actions" onClick={(e) => e.stopPropagation()}>
            <button
              className="icon-btn"
              title="New subfolder"
              onClick={() => {
                setCreatingUnder(folder.id)
                setNewName('')
              }}
            >
              +
            </button>
            <button
              className="icon-btn"
              title="Rename"
              onClick={() => {
                setRenaming(folder)
                setNewName(folder.name)
              }}
            >
              ✎
            </button>
            <button
              className="icon-btn"
              title="Delete"
              onClick={() => {
                if (window.confirm(`Delete folder "${folder.name}"? It must be empty.`)) {
                  deleteFolder(kind, folder.id)
                    .then(onFoldersChanged)
                    .catch((err: Error) => setError(err.message))
                }
              }}
            >
              ✕
            </button>
          </span>
        </div>
        {creatingUnder === folder.id && (
          <div className="folder-input-row" style={{ paddingLeft: 24 + depth * 14 }}>
            <input
              type="text"
              value={newName}
              autoFocus
              placeholder="Folder name"
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitCreate()
                if (e.key === 'Escape') setCreatingUnder(null)
              }}
            />
          </div>
        )}
        {childrenOf(folder.id).map((child) => renderRow(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="folder-tree">
      <div
        className={`folder-row ${selectedId === null ? 'selected' : ''}`}
        style={{ paddingLeft: 10 }}
        onClick={() => onSelect(null)}
      >
        <span className="folder-name">All</span>
        <span className="folder-actions" onClick={(e) => e.stopPropagation()}>
          <button
            className="icon-btn"
            title="New folder"
            onClick={() => {
              setCreatingUnder('root')
              setNewName('')
            }}
          >
            +
          </button>
        </span>
      </div>
      {creatingUnder === 'root' && (
        <div className="folder-input-row" style={{ paddingLeft: 24 }}>
          <input
            type="text"
            value={newName}
            autoFocus
            placeholder="Folder name"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitCreate()
              if (e.key === 'Escape') setCreatingUnder(null)
            }}
          />
        </div>
      )}
      {childrenOf(null).map((folder) => renderRow(folder, 0))}
      {error && <div className="form-error folder-error">{error}</div>}
      {renaming && (
        <div className="inline-rename">
          <input
            type="text"
            value={newName}
            autoFocus
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setRenaming(null)
            }}
          />
          <button className="btn" onClick={commitRename}>
            Save
          </button>
          <button className="btn secondary" onClick={() => setRenaming(null)}>
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}
