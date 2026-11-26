import { useEffect, useState } from 'react'
import { Dialog } from '../Dialog'

interface ConfirmDialogProps {
  title: string
  message: string
  confirmLabel?: string
  onConfirm: () => Promise<void> | void
  onClose: () => void
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Delete',
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
      onClose()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title={title} onClose={onClose}>
      <p className="dialog-message">{message}</p>
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn danger" onClick={confirm} disabled={busy}>
          {busy ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}
