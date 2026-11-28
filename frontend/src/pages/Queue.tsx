import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { AddToGalleryDialog } from '../components/AddToGalleryDialog'
import { ConfirmDialog } from '../components/ConfirmDialog'
import type { CompareImage } from '../components/ImageComparison'
import { JobResultViewer } from '../components/JobResultViewer'
import { MoveToLibraryDialog } from '../components/MoveToLibraryDialog'
import { useAddToGallery } from '../hooks/useAddToGallery'
import { useMoveToLibrary } from '../hooks/useMoveToLibrary'
import { listAssets } from '../services/assets'
import {
  cancelJob,
  deleteJobOutput,
  listJobs,
  removeJob,
} from '../services/jobs'
import type { AssetFile } from '../types/assets'
import {
  NOT_STARTED_STATUSES,
  statusLabel,
  TERMINAL_STATUSES,
  type Job,
} from '../types/jobs'

const POLL_INTERVAL_MS = 2500
const RECENT_LIMIT = 25

const CATEGORY_LABEL: Record<string, string> = {
  general_generation: 'General Generation',
  image_modification: 'Image Modification',
  character_swap: 'Character Swap',
}

function parseServerDate(iso: string | null): number | null {
  if (!iso) return null
  const withZone = /([+\-]\d{2}:?\d{2}|Z)$/.test(iso) ? iso : `${iso}Z`
  const t = new Date(withZone).getTime()
  return Number.isFinite(t) ? t : null
}

function fmtClock(iso: string | null): string {
  const t = parseServerDate(iso)
  if (t == null) return ''
  return new Date(t).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function Queue() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sourceFiles, setSourceFiles] = useState<Map<number, AssetFile>>(new Map())
  const [clearedAt, setClearedAt] = useState(0)
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{
    clientId: string
    outputId: number
  } | null>(null)

  const upsertJob = useCallback((fresh: Job) => {
    setJobs((prev) => [
      fresh,
      ...prev.filter((j) => j.client_id !== fresh.client_id),
    ])
  }, [])
  const { moveTarget, requestMove, handleMove, handleAddToExisting, closeMove } =
    useMoveToLibrary(upsertJob)
  const { target: galleryTarget, requestAdd, closeAdd } = useAddToGallery()

  const refreshSourceFiles = useCallback(() => {
    Promise.all([listAssets('scene'), listAssets('character')])
      .then(([scenes, characters]) => {
        const map = new Map<number, AssetFile>()
        for (const a of [...scenes, ...characters])
          for (const f of a.files) map.set(f.id, f)
        setSourceFiles(map)
      })
      .catch(() => {
        // Comparison degrades to generated-only if assets can't be listed.
      })
  }, [])

  useEffect(() => {
    refreshSourceFiles()
  }, [refreshSourceFiles])

  // Poll the whole job list (all categories) while the tab is open.
  useEffect(() => {
    let stopped = false
    async function tick() {
      try {
        const list = await listJobs({ limit: 100 })
        if (!stopped) {
          setJobs(list)
          setLoadError(null)
        }
      } catch (e) {
        if (!stopped) setLoadError((e as Error).message)
      }
    }
    tick()
    const timer = setInterval(tick, POLL_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [])

  const running = jobs.filter((j) => j.status === 'running')
  const queued = jobs.filter(
    (j) =>
      j.status === 'pending' || j.status === 'dispatching' || j.status === 'queued',
  )
  const recent = useMemo(
    () =>
      jobs
        .filter((j) => TERMINAL_STATUSES.includes(j.status))
        .filter((j) => {
          const t = parseServerDate(j.finished_at)
          return clearedAt === 0 || (t != null && t > clearedAt)
        })
        .slice(0, RECENT_LIMIT),
    [jobs, clearedAt],
  )

  const selectedJob = jobs.find((j) => j.client_id === selectedClientId) ?? null

  // Drop the selection if the job was removed from the list.
  useEffect(() => {
    if (selectedClientId && !jobs.some((j) => j.client_id === selectedClientId)) {
      setSelectedClientId(null)
    }
  }, [jobs, selectedClientId])

  // Auto-select a job once on first load so the viewer isn't empty.
  const autoSelected = useRef(false)
  useEffect(() => {
    if (autoSelected.current || jobs.length === 0) return
    autoSelected.current = true
    const pick =
      running[0] ??
      queued[0] ??
      jobs.find((j) => TERMINAL_STATUSES.includes(j.status)) ??
      null
    if (pick) setSelectedClientId(pick.client_id)
  }, [jobs, running, queued])

  function originalFor(job: Job): CompareImage | null {
    const src =
      job.category === 'character_swap'
        ? job.inputs.scene_image
        : job.inputs.source_image
    if (!src || typeof src !== 'object') return null
    const ref = src as { asset_file_id?: number }
    const file = sourceFiles.get(ref.asset_file_id ?? -1)
    if (!file) return null
    return {
      src: file.original_url,
      width: file.width,
      height: file.height,
      alt: file.display_name,
    }
  }

  async function handleCancel(clientId: string) {
    try {
      const fresh = await cancelJob(clientId)
      upsertJob(fresh)
    } catch (e) {
      setLoadError((e as Error).message)
    }
  }

  async function handleRemove(clientId: string) {
    try {
      await removeJob(clientId)
      if (selectedClientId === clientId) setSelectedClientId(null)
    } catch (e) {
      setLoadError((e as Error).message)
    }
  }

  // One "stop" action for the viewer: remove not-started jobs, cancel started ones.
  async function handleStop(clientId: string) {
    const job = jobs.find((j) => j.client_id === clientId)
    if (job && NOT_STARTED_STATUSES.includes(job.status)) {
      await handleRemove(clientId)
    } else {
      await handleCancel(clientId)
    }
  }

  async function handleDeleteConfirmed() {
    if (!confirmDelete) return
    const { clientId, outputId } = confirmDelete
    try {
      const fresh = await deleteJobOutput(clientId, outputId)
      upsertJob(fresh)
    } catch (e) {
      setLoadError((e as Error).message)
    }
  }

  const viewerNonTerminal = selectedJob
    ? !TERMINAL_STATUSES.includes(selectedJob.status)
    : false
  const viewerCompleted = selectedJob?.status === 'completed'

  function renderRow(job: Job, kind: 'running' | 'queued' | 'recent') {
    const notStarted = NOT_STARTED_STATUSES.includes(job.status)
    const showProgress = kind === 'running' || kind === 'queued'
    return (
      <div
        key={job.client_id}
        role="button"
        tabIndex={0}
        className={`queue-row ${selectedClientId === job.client_id ? 'selected' : ''}`}
        onClick={() => setSelectedClientId(job.client_id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') setSelectedClientId(job.client_id)
        }}
      >
        <div className="queue-row-top">
          <span className={`job-state job-state--${job.status}`}>
            {statusLabel(job.status)}
          </span>
          <span className="queue-row-kind">
            {CATEGORY_LABEL[job.category] ?? job.workflow_name}
          </span>
          <span className="queue-row-time">
            {kind === 'recent' ? fmtClock(job.finished_at) : fmtClock(job.created_at)}
          </span>
          {notStarted ? (
            <button
              type="button"
              className="btn secondary"
              onClick={(e) => {
                e.stopPropagation()
                setConfirmRemove(job.client_id)
              }}
            >
              Remove
            </button>
          ) : viewerNonTerminalFor(job) ? (
            <button
              type="button"
              className="btn secondary"
              onClick={(e) => {
                e.stopPropagation()
                void handleCancel(job.client_id)
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
        <div className="queue-row-prompt">
          {job.prompt || job.workflow_name}
        </div>
        {job.status === 'failed' && job.error && (
          <div className="queue-row-error">{job.error}</div>
        )}
        {showProgress && (
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${Math.round(job.progress * 100)}%` }}
            />
          </div>
        )}
      </div>
    )
  }

  function viewerNonTerminalFor(job: Job): boolean {
    return !TERMINAL_STATUSES.includes(job.status)
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Queue</h1>
      </header>

      {loadError && <div className="test-result off">{loadError}</div>}

      <div className="queue-layout">
        <section className="queue" aria-label="Queue">
          <div className="queue-section">
            <h2 className="queue-section-title">
              Running <span className="queue-count">{running.length}</span>
            </h2>
            {running.length === 0 ? (
              <p className="queue-empty">Nothing running.</p>
            ) : (
              <div className="queue-list">{running.map((j) => renderRow(j, 'running'))}</div>
            )}
          </div>

          <div className="queue-section">
            <h2 className="queue-section-title">
              Queued <span className="queue-count">{queued.length}</span>
            </h2>
            {queued.length === 0 ? (
              <p className="queue-empty">Nothing waiting in the queue.</p>
            ) : (
              <div className="queue-list">{queued.map((j) => renderRow(j, 'queued'))}</div>
            )}
          </div>

          <div className="queue-section">
            <div className="queue-section-head">
              <h2 className="queue-section-title">
                Recent <span className="queue-count">{recent.length}</span>
              </h2>
              {recent.length > 0 && (
                <button
                  type="button"
                  className="btn secondary small"
                  onClick={() => setClearedAt(Date.now())}
                  title="Clears the recent list in this view only; it does not delete jobs or their images."
                >
                  Clear
                </button>
              )}
            </div>
            {recent.length === 0 ? (
              <p className="queue-empty">No recent completed or failed jobs.</p>
            ) : (
              <div className="queue-list">
                {recent.map((j) => renderRow(j, 'recent'))}
              </div>
            )}
          </div>
        </section>

        <section aria-label="Selected job">
          {selectedJob ? (
            <JobResultViewer
              job={selectedJob}
              original={originalFor(selectedJob)}
              onCancel={viewerNonTerminal ? handleStop : undefined}
              onDeleteOutput={
                viewerCompleted ? (cid, oid) => setConfirmDelete({ clientId: cid, outputId: oid }) : undefined
              }
              onMoveOutput={viewerCompleted ? requestMove : undefined}
              onAddToGallery={viewerCompleted ? requestAdd : undefined}
            />
          ) : (
            <div className="gen-empty">
              <div className="placeholder-glyph">◈</div>
              <p>Select a job to view its details and results.</p>
            </div>
          )}
        </section>
      </div>

      {moveTarget && (
        <MoveToLibraryDialog
          onMove={handleMove}
          onAddToExisting={handleAddToExisting}
          onClose={closeMove}
        />
      )}

      {galleryTarget && (
        <AddToGalleryDialog outputId={galleryTarget.outputId} onClose={closeAdd} />
      )}

      {confirmRemove && (
        <ConfirmDialog
          title="Remove queued job?"
          message="This removes the job from the queue. It has not started, so no images were produced and nothing else is deleted."
          onConfirm={async () => {
            const cid = confirmRemove
            setConfirmRemove(null)
            await handleRemove(cid)
          }}
          onClose={() => setConfirmRemove(null)}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete generated image?"
          message="This permanently removes the selected generated image and its thumbnail. Other outputs and your source assets are not affected."
          onConfirm={handleDeleteConfirmed}
          onClose={() => setConfirmDelete(null)}
        />
      )}
    </div>
  )
}
