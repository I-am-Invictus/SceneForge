import { useRef, useState } from 'react'
import type { AssetKind, Folder } from '../types/assets'
import { createAssets } from '../services/assets'
import { Dialog } from './Dialog'
import { FolderPicker } from './FolderPicker'

interface NewAssetDialogProps {
  kind: AssetKind
  folders: Folder[]
  onCreated: (ids: number[]) => void
  onClose: () => void
}

const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'

export function NewAssetDialog({
  kind,
  folders,
  onCreated,
  onClose,
}: NewAssetDialogProps) {
  const isCharacter = kind === 'character'
  const [name, setName] = useState('')
  const [folderId, setFolderId] = useState<number | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const created = await createAssets(
        kind,
        files,
        isCharacter ? name : undefined,
        folderId,
      )
      onCreated(created.map((a) => a.id))
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const canSubmit = files.length > 0 && (!isCharacter || name.trim().length > 0)

  return (
    <Dialog
      title={isCharacter ? 'New Character' : 'New Scene'}
      onClose={onClose}
    >
      {isCharacter && (
        <label className="field">
          <span>Name</span>
          <input
            type="text"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Aria"
          />
        </label>
      )}
      <span className="field-label">Folder</span>
      <FolderPicker folders={folders} value={folderId} onChange={setFolderId} />
      <span className="field-label">
        Images {isCharacter ? '(one or more references)' : '(each image becomes a scene)'}
      </span>
      <button
        type="button"
        className="file-drop"
        onClick={() => inputRef.current?.click()}
      >
        {files.length > 0
          ? `${files.length} file${files.length === 1 ? '' : 's'} selected`
          : 'Click to choose images'}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </button>
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn" onClick={submit} disabled={busy || !canSubmit}>
          {busy ? 'Uploading…' : isCharacter ? 'Create' : 'Add'}
        </button>
      </div>
    </Dialog>
  )
}
