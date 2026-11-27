import { Icon } from './icons'
import type { Job } from '../types/jobs'

function parseServerDate(iso: string): number {
  const withZone = /([+\-]\d{2}:?\d{2}|Z)$/.test(iso) ? iso : `${iso}Z`
  const t = new Date(withZone).getTime()
  return Number.isFinite(t) ? t : Date.now()
}

function timeAgo(iso: string): string {
  const secs = Math.max(0, Math.floor((Date.now() - parseServerDate(iso)) / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

interface JobGalleryProps {
  /** Completed jobs with at least one output, newest first. */
  jobs: Job[]
  selectedClientId?: string | null
  onSelect: (clientId: string) => void
  /** When provided, each card shows a delete action for its displayed
   *  (first) output. The parent handles confirmation. */
  onDelete?: (clientId: string, outputId: number) => void
  /** When provided, each card shows a move-to-library action for its
   *  displayed (first) output. */
  onMove?: (clientId: string, outputId: number) => void
  /** When provided, each card shows an add-to-gallery action for its
   *  displayed (first) output. */
  onAddToGallery?: (clientId: string, outputId: number) => void
}

export function JobGallery({
  jobs,
  selectedClientId,
  onSelect,
  onDelete,
  onMove,
  onAddToGallery,
}: JobGalleryProps) {
  if (jobs.length === 0) return null
  return (
    <div className="job-gallery">
      {jobs.map((job) => (
        <div
          key={job.client_id}
          role="button"
          tabIndex={0}
          className={`job-gallery-card ${
            selectedClientId === job.client_id ? 'selected' : ''
          }`}
          onClick={() => onSelect(job.client_id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSelect(job.client_id)
          }}
          title={job.prompt ?? undefined}
        >
          <div className="job-gallery-thumb">
            <img src={job.outputs[0].thumbnail_url} alt="" loading="lazy" />
            {onMove && (
              <button
                type="button"
                className="card-move"
                aria-label="Move this generated image to a library"
                onClick={(e) => {
                  e.stopPropagation()
                  onMove(job.client_id, job.outputs[0].id)
                }}
              >
                <Icon name="moveToLibrary" size={14} />
              </button>
            )}
            {onAddToGallery && (
              <button
                type="button"
                className="card-move"
                aria-label="Add this generated image to a gallery"
                onClick={(e) => {
                  e.stopPropagation()
                  onAddToGallery(job.client_id, job.outputs[0].id)
                }}
              >
                <Icon name="galleries" size={14} />
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                className="card-delete"
                aria-label="Delete this generated image"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(job.client_id, job.outputs[0].id)
                }}
              >
                <Icon name="trash" size={14} />
              </button>
            )}
          </div>
          <div className="job-gallery-foot">
            <span className="job-gallery-prompt">{job.prompt || job.workflow_name}</span>
            <span className="job-gallery-time">{timeAgo(job.created_at)}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
