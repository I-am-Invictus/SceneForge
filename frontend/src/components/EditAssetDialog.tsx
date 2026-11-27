import { useEffect, useState } from 'react'
import { Dialog } from './Dialog'

interface EditAssetDialogProps {
  title: string
  initialName: string
  initialDescription: string | null
  initialTags: string[]
  onSave: (
    name: string,
    description: string,
    tags: string[],
  ) => Promise<void>
  onClose: () => void
}

function parseTags(text: string): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const raw of text.split(',')) {
    const tag = raw.trim()
    if (tag && !seen.has(tag)) {
      seen.add(tag)
      result.push(tag)
    }
  }
  return result
}

export function EditAssetDialog({
  title,
  initialName,
  initialDescription,
  initialTags,
  onSave,
  onClose,
}: EditAssetDialogProps) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription ?? '')
  const [tagsText, setTagsText] = useState(initialTags.join(', '))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setName(initialName)
    setDescription(initialDescription ?? '')
    setTagsText(initialTags.join(', '))
  }, [initialName, initialDescription, initialTags])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSave(name, description, parseTags(tagsText))
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
        />
      </label>
      <label className="field">
        <span>Description</span>
        <textarea
          className="form-textarea"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional notes about this asset…"
        />
      </label>
      <label className="field">
        <span>Tags</span>
        <input
          type="text"
          value={tagsText}
          onChange={(e) => setTagsText(e.target.value)}
          placeholder="comma-separated, e.g. hero, classic"
        />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn" onClick={submit} disabled={busy || !name.trim()}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Dialog>
  )
}
