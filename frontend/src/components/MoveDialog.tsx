import { useState } from 'react'
import type { Folder } from '../types/assets'
import { Dialog } from './Dialog'
import { FolderPicker } from './FolderPicker'

interface MoveDialogProps {
  title: string
  folders: Folder[]
  initialFolderId: number | null
  onMove: (folderId: number | null) => Promise<void>
  onClose: () => void
}

export function MoveDialog({
  title,
  folders,
  initialFolderId,
  onMove,
  onClose,
}: MoveDialogProps) {
  const [folderId, setFolderId] = useState<number | null>(initialFolderId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onMove(folderId)
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title={title} onClose={onClose}>
      <span className="field-label">Move to</span>
      <FolderPicker folders={folders} value={folderId} onChange={setFolderId} />
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn" onClick={submit} disabled={busy}>
          {busy ? 'Moving…' : 'Move'}
        </button>
      </div>
    </Dialog>
  )
}
