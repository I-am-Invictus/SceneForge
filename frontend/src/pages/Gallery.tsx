import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createGallery, listGalleries } from '../services/galleries'
import type { Gallery } from '../types/galleries'

export function Gallery() {
  const navigate = useNavigate()
  const [galleries, setGalleries] = useState<Gallery[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listGalleries().then(setGalleries).catch(() => setGalleries([]))
  }, [])

  async function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await createGallery(trimmed)
      setGalleries((prev) =>
        [...(prev ?? []), created].sort((a, b) => a.name.localeCompare(b.name)),
      )
      setName('')
      setCreating(false)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Galleries</h1>
        <button className="btn" onClick={() => setCreating((v) => !v)}>
          + New gallery
        </button>
      </header>

      {creating && (
        <div className="gallery-create gallery-create--page">
          <input
            autoFocus
            value={name}
            placeholder="Gallery name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleCreate()
            }}
          />
          <button
            className="btn"
            onClick={() => void handleCreate()}
            disabled={busy || !name.trim()}
          >
            {busy ? 'Creating…' : 'Create'}
          </button>
          <button
            className="btn secondary"
            onClick={() => {
              setCreating(false)
              setName('')
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}

      {galleries === null ? (
        <p className="empty-note">Loading galleries…</p>
      ) : galleries.length === 0 ? (
        <p className="empty-note">
          No galleries yet. Create one, or add images to a gallery from any job
          result.
        </p>
      ) : (
        <div className="gallery-grid">
          {galleries.map((g) => (
            <div
              key={g.id}
              className="gallery-card"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/galleries/${g.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') navigate(`/galleries/${g.id}`)
              }}
            >
              <div className="gallery-card-cover">
                {g.cover ? (
                  <img
                    src={g.cover.thumbnail_url}
                    alt={g.cover.label}
                    loading="lazy"
                  />
                ) : (
                  <span className="gallery-card-empty">No images</span>
                )}
              </div>
              <div className="gallery-card-foot">
                <span className="gallery-card-name">{g.name}</span>
                <span className="gallery-card-count">
                  {g.image_count} image{g.image_count === 1 ? '' : 's'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
