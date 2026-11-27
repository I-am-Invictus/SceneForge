import { useEffect, useState } from 'react'
import { Dialog } from './Dialog'
import {
  createGallery,
  getOutputGalleries,
  listGalleries,
  syncOutputGalleries,
} from '../services/galleries'
import type { Gallery } from '../types/galleries'

interface AddToGalleryDialogProps {
  outputId: number
  onClose: () => void
}

export function AddToGalleryDialog({
  outputId,
  onClose,
}: AddToGalleryDialogProps) {
  const [galleries, setGalleries] = useState<Gallery[] | null>(null)
  const [checked, setChecked] = useState<Set<number>>(new Set())
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listGalleries(), getOutputGalleries(outputId)])
      .then(([all, current]) => {
        if (cancelled) return
        setGalleries(all)
        setChecked(new Set(current.map((g) => g.id)))
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [outputId])

  function toggle(id: number) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleCreate() {
    const name = newName.trim()
    if (!name || creating) return
    setCreating(true)
    setError(null)
    try {
      const created = await createGallery(name)
      setGalleries((prev) => [...(prev ?? []), created].sort((a, b) => a.name.localeCompare(b.name)))
      setChecked((prev) => new Set(prev).add(created.id))
      setNewName('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCreating(false)
    }
  }

  async function handleSave() {
    setBusy(true)
    setError(null)
    try {
      await syncOutputGalleries(outputId, Array.from(checked))
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title="Add to gallery" onClose={onClose}>
      <p className="dialog-sub">
        Choose which collections this image belongs to. It can sit in several
        at once, or in none.
      </p>
      {galleries === null && !error ? (
        <p className="empty-note">Loading galleries…</p>
      ) : (
        <>
          {galleries && galleries.length > 0 ? (
            <div className="gallery-check-list">
              {galleries.map((g) => (
                <label
                  key={g.id}
                  className={`gallery-check ${checked.has(g.id) ? 'checked' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={checked.has(g.id)}
                    onChange={() => toggle(g.id)}
                    disabled={busy}
                  />
                  <span className="gallery-check-name">{g.name}</span>
                  <span className="gallery-check-count">{g.image_count}</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="empty-note">No galleries yet — create one below.</p>
          )}
          <div className="gallery-create">
            <input
              value={newName}
              placeholder="New gallery name"
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleCreate()
              }}
              disabled={busy || creating}
            />
            <button
              type="button"
              className="btn secondary"
              onClick={() => void handleCreate()}
              disabled={busy || creating || !newName.trim()}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </div>
        </>
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn" onClick={() => void handleSave()} disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Dialog>
  )
}
