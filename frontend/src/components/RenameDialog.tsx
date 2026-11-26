import { useEffect, useState } from 'react'
import { Dialog } from '../Dialog'

interface RenameDialogProps {
  title: string
  initialName: string
  onRename: (name: string) => Promise<void>
  onClose: () => void
}

export function RenameDialog({
  title,
  initialName,
  onRename,
  onClose,
}: RenameDialogProps) {
  const [name, setName] = useState(initialName)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setName(initialName)
  }, [initialName])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onRename(name)
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title={title} onClose={onClose}>
      <label className="field">
        <span>Name</span>
        <input
          type="text"
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn" onClick={submit} disabled={busy || !name.trim()}>
          {busy ? 'Saving…' : 'Rename'}
        </button>
      </div>
    </Dialog>
  )
}
