import { useState } from 'react'
import { Dialog } from './Dialog'
import { Icon } from './icons'
import type { AssetKind } from '../types/assets'

interface MoveToLibraryDialogProps {
  onMove: (folder: AssetKind) => Promise<void>
  onClose: () => void
}

const OPTIONS: { kind: AssetKind; label: string; icon: 'characters' | 'scenes' }[] = [
  { kind: 'character', label: 'Characters', icon: 'characters' },
  { kind: 'scene', label: 'Scenes', icon: 'scenes' },
]

export function MoveToLibraryDialog({
  onMove,
  onClose,
}: MoveToLibraryDialogProps) {
  const [busy, setBusy] = useState<AssetKind | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleMove(kind: AssetKind) {
    setBusy(kind)
    setError(null)
    try {
      await onMove(kind)
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  return (
    <Dialog title="Move image to library" onClose={onClose}>
      <p className="dialog-sub">
        The image is preserved and stays in this job&rsquo;s results and in
        generation history. It will also appear in the chosen library.
      </p>
      <div className="move-options">
        {OPTIONS.map((option) => (
          <button
            key={option.kind}
            type="button"
            className="move-option"
            disabled={busy !== null}
            onClick={() => void handleMove(option.kind)}
          >
            <Icon name={option.icon} size={20} />
            <span>{busy === option.kind ? 'Moving…' : option.label}</span>
          </button>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
    </Dialog>
  )
}
