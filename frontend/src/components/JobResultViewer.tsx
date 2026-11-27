import { useEffect, useState } from 'react'
import type { Job } from '../types/jobs'
import { Icon } from './icons'
import { ImageComparison, type CompareImage } from './ImageComparison'

function parseServerDate(iso: string | null): number | null {
  if (!iso) return null
  // The backend stores UTC datetimes without an offset; treat bare ISO as UTC.
  const withZone = /([+\-]\d{2}:?\d{2}|Z)$/.test(iso) ? iso : `${iso}Z`
  const t = new Date(withZone).getTime()
  return Number.isFinite(t) ? t : null
}

function formatDuration(job: Job): string {
  const start = parseServerDate(job.started_at ?? job.created_at)
  const end = parseServerDate(job.finished_at)
  if (start == null || end == null) return ''
  const secs = Math.max(0, Math.round((end - start) / 1000))
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return s ? `${m}m ${s}s` : `${m}m`
}

function MetaRow({ job }: { job: Job }) {
  const chips: string[] = []
  if (job.inputs.width != null && job.inputs.height != null) {
    chips.push(`${job.inputs.width}×${job.inputs.height}`)
  }
  if (job.inputs.seed != null) chips.push(`seed ${job.inputs.seed}`)
  if (job.inputs.steps != null) chips.push(`${job.inputs.steps} steps`)
  if (job.inputs.cfg != null) chips.push(`cfg ${job.inputs.cfg}`)
  return (
    <div className="job-meta">
      {job.prompt && <p className="job-viewer-prompt">{job.prompt}</p>}
      {chips.length > 0 && (
        <div className="job-chips">
          {chips.map((c) => (
            <span key={c} className="job-chip">
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

interface JobResultViewerProps {
  job: Job
  /** Original image associated with this job's outputs (e.g. the source
   *  asset for image modification / person swap). Null for general
   *  generation — the comparison view degrades to generated-only. */
  original: CompareImage | null
  onPrev?: () => void
  onNext?: () => void
  canPrev?: boolean
  canNext?: boolean
  onCancel?: (clientId: string) => void
  /** When provided, shows a delete action for the currently displayed
   *  output. The parent is responsible for confirmation. */
  onDeleteOutput?: (clientId: string, outputId: number) => void
  /** When provided, shows a move-to-library action for the currently
   *  displayed output. */
  onMoveOutput?: (clientId: string, outputId: number) => void
  /** When provided, shows an add-to-gallery action for the currently
   *  displayed output. */
  onAddToGallery?: (clientId: string, outputId: number) => void
}

export function JobResultViewer({
  job,
  original,
  onPrev,
  onNext,
  canPrev,
  canNext,
  onCancel,
  onDeleteOutput,
  onMoveOutput,
  onAddToGallery,
}: JobResultViewerProps) {
  const [outputIndex, setOutputIndex] = useState(0)
  useEffect(() => {
    setOutputIndex(0)
  }, [job.client_id])

  const head = (
    <div className="job-viewer-head">
      <span className={`job-state job-state--${job.status}`}>{job.status}</span>
      <span className="job-viewer-title">
        {job.workflow_name} v{job.workflow_version}
      </span>
      <span className="job-viewer-time">{formatDuration(job)}</span>
    </div>
  )

  if (job.status === 'queued' || job.status === 'running') {
    return (
      <div className="job-viewer job-viewer--active">
        {head}
        {onCancel && (
          <div className="job-viewer-cancel">
            <button
              type="button"
              className="btn secondary"
              onClick={() => onCancel(job.client_id)}
            >
              Cancel
            </button>
          </div>
        )}
        {job.prompt && <p className="job-viewer-prompt">{job.prompt}</p>}
        <div className="progress">
          <div
            className="progress-bar"
            style={{ width: `${Math.round(job.progress * 100)}%` }}
          />
        </div>
        <div className="job-viewer-sub">
          {Math.round(job.progress * 100)}% · {job.status} on ComfyUI
        </div>
      </div>
    )
  }

  if (job.status !== 'completed') {
    return (
      <div className="job-viewer job-viewer--failed">
        {head}
        {job.error && <p className="job-viewer-error">{job.error}</p>}
        {job.prompt && <p className="job-viewer-prompt">{job.prompt}</p>}
      </div>
    )
  }

  const output =
    job.outputs.length > 0
      ? job.outputs[Math.min(outputIndex, job.outputs.length - 1)]
      : null

  if (!output) {
    return (
      <div className="job-viewer">
        {head}
        <div className="empty-note">No image outputs were produced.</div>
      </div>
    )
  }

  const generated: CompareImage = {
    src: output.original_url,
    alt: output.comfyui_filename,
    width: output.width ?? undefined,
    height: output.height ?? undefined,
  }

  return (
    <div className="job-viewer job-viewer--done">
      {head}
      <ImageComparison
        original={original}
        generated={generated}
        resultKey={`${job.client_id}:${outputIndex}`}
        onPrev={onPrev}
        onNext={onNext}
        canPrev={canPrev}
        canNext={canNext}
      />
      <div className="job-viewer-toolbar">
        {job.outputs.length > 1 && (
          <span className="output-count">
            Result {outputIndex + 1} of {job.outputs.length}
          </span>
        )}
        {onMoveOutput && (
          <button
            type="button"
            className="btn secondary job-delete-btn"
            onClick={() => onMoveOutput(job.client_id, output.id)}
          >
            <Icon name="moveToLibrary" size={14} />
            Move to library
          </button>
        )}
        {onAddToGallery && (
          <button
            type="button"
            className="btn secondary job-delete-btn"
            onClick={() => onAddToGallery(job.client_id, output.id)}
          >
            <Icon name="galleries" size={14} />
            Add to gallery
          </button>
        )}
        {onDeleteOutput && (
          <button
            type="button"
            className="btn secondary job-delete-btn"
            onClick={() => onDeleteOutput(job.client_id, output.id)}
          >
            <Icon name="trash" size={14} />
            Delete image
          </button>
        )}
      </div>
      {job.outputs.length > 1 && (
        <div className="output-picker">
          {job.outputs.map((o, i) => (
            <button
              key={o.id}
              type="button"
              className={`output-thumb ${i === outputIndex ? 'active' : ''}`}
              onClick={() => setOutputIndex(i)}
              aria-label={`Show output ${i + 1} of ${job.outputs.length}`}
            >
              <img src={o.thumbnail_url} alt="" />
            </button>
          ))}
        </div>
      )}
      <MetaRow job={job} />
    </div>
  )
}
