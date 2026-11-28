import { useCallback, useEffect, useState } from 'react'
import { AddToGalleryDialog } from '../components/AddToGalleryDialog'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { JobGallery } from '../components/JobGallery'
import { JobResultViewer } from '../components/JobResultViewer'
import { MoveToLibraryDialog } from '../components/MoveToLibraryDialog'
import { useAddToGallery } from '../hooks/useAddToGallery'
import { useMoveToLibrary } from '../hooks/useMoveToLibrary'
import {
  cancelJob,
  deleteJobOutput,
  generate,
  getJob,
  listJobs,
  listWorkflows,
} from '../services/jobs'
import { TERMINAL_STATUSES, type Job, type Workflow } from '../types/jobs'

const SIZE_PRESETS = [
  { id: '1:1', label: '1:1', width: 1024, height: 1024 },
  { id: '3:4', label: '3:4', width: 896, height: 1152 },
  { id: '4:3', label: '4:3', width: 1152, height: 896 },
  { id: '9:16', label: '9:16', width: 864, height: 1536 },
  { id: '16:9', label: '16:9', width: 1536, height: 864 },
]

const POLL_INTERVAL_MS = 2500

function roundTo8(value: number, minimum = 16, maximum = 2048): number {
  const rounded = Math.round(value / 8) * 8
  return Math.min(maximum, Math.max(minimum, rounded))
}

export function GeneralGeneration() {
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [activeJobs, setActiveJobs] = useState<Job[]>([])
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [prompt, setPrompt] = useState('')
  const [negative, setNegative] = useState('')
  const [sizeId, setSizeId] = useState('3:4')
  const [widthText, setWidthText] = useState('896')
  const [heightText, setHeightText] = useState('1152')
  const [randomSeed, setRandomSeed] = useState(true)
  const [seedText, setSeedText] = useState('')
  const [stepsText, setStepsText] = useState('4')
  const [cfgText, setCfgText] = useState('1')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
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

  const workflow =
    workflows?.find((w) => w.category === 'general_generation' && w.enabled) ??
    null

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const wfs = await listWorkflows()
        if (cancelled) return
        setWorkflows(wfs)
        const gen = wfs.find(
          (w) => w.category === 'general_generation' && w.enabled,
        )
        if (gen) {
          const list = await listJobs({ workflow_id: gen.id, limit: 60 })
          if (!cancelled) setJobs(list)
        }
      } catch (e) {
        if (!cancelled) setLoadError((e as Error).message)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (activeJobs.length === 0) return
    let stopped = false
    const timer = setInterval(async () => {
      const stillActive: Job[] = []
      for (const job of activeJobs) {
        try {
          const fresh = await getJob(job.client_id)
          if (stopped) return
          if (TERMINAL_STATUSES.includes(fresh.status)) {
            setJobs((prev) => [
              fresh,
              ...prev.filter((j) => j.client_id !== fresh.client_id),
            ])
            if (fresh.status === 'completed') {
              setSelectedClientId(fresh.client_id)
            }
          } else {
            stillActive.push(fresh)
          }
        } catch {
          stillActive.push(job)
        }
      }
      if (!stopped) setActiveJobs(stillActive)
    }, POLL_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [activeJobs])

  async function handleGenerate() {
    if (!workflow || submitting) return
    setSubmitting(true)
    setFormError(null)
    try {
      const width = roundTo8(Number(widthText))
      const height = roundTo8(Number(heightText))
      if (!Number.isFinite(width) || !Number.isFinite(height)) {
        setFormError('Width and height must be numbers.')
        return
      }
      const steps = Number(stepsText)
      const cfg = Number(cfgText)
      if (!Number.isFinite(steps) || steps < 1) {
        setFormError('Steps must be a positive number.')
        return
      }
      if (!Number.isFinite(cfg) || cfg <= 0) {
        setFormError('CFG must be a positive number.')
        return
      }
      let seed: string | number = 'random'
      if (!randomSeed && seedText.trim() !== '') {
        const parsed = Number(seedText)
        if (!Number.isInteger(parsed)) {
          setFormError('Seed must be a whole number.')
          return
        }
        seed = parsed
      }
      const inputs: Record<string, unknown> = {
        prompt: prompt.trim(),
        width,
        height,
        seed,
        steps,
        cfg,
      }
      if (negative.trim()) inputs.negative_prompt = negative.trim()
      const job = await generate(workflow.id, inputs)
      setActiveJobs((prev) => [job, ...prev])
      setSelectedClientId(job.client_id)
      setPrompt('')
    } catch (e) {
      setFormError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCancel(clientId: string) {
    try {
      const fresh = await cancelJob(clientId)
      setActiveJobs((prev) =>
        prev.map((j) => (j.client_id === clientId ? fresh : j)),
      )
      upsertJob(fresh)
    } catch (e) {
      setFormError((e as Error).message)
    }
  }

  async function handleDeleteConfirmed() {
    if (!confirmDelete) return
    const { clientId, outputId } = confirmDelete
    const fresh = await deleteJobOutput(clientId, outputId)
    upsertJob(fresh)
  }

  const requestDelete = (clientId: string, outputId: number) => {
    setConfirmDelete({ clientId, outputId })
  }

  function applyPreset(id: string) {
    const preset = SIZE_PRESETS.find((p) => p.id === id)
    if (!preset) return
    setSizeId(id)
    setWidthText(String(preset.width))
    setHeightText(String(preset.height))
  }

  const results = jobs.filter(
    (j) => j.status === 'completed' && j.outputs.length > 0,
  )
  const selectedJob =
    jobs.find((j) => j.client_id === selectedClientId) ??
    activeJobs.find((j) => j.client_id === selectedClientId) ??
    null
  const viewerJob = selectedJob ?? (results[0] ?? null)
  const viewerIndex = viewerJob
    ? results.findIndex((j) => j.client_id === viewerJob.client_id)
    : -1
  const canPrev = viewerIndex >= 0 && viewerIndex < results.length - 1
  const canNext = viewerIndex > 0
  const goPrev = () => {
    if (canPrev) setSelectedClientId(results[viewerIndex + 1].client_id)
  }
  const goNext = () => {
    if (canNext) setSelectedClientId(results[viewerIndex - 1].client_id)
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>General Generation</h1>
      </header>

      {loadError && <div className="test-result off">{loadError}</div>}

      <div className="gen-layout">
        <section className="gen-form" aria-label="Generation settings">
          <h2>New image</h2>
          <p className="gen-form-sub">
            {workflow
              ? `${workflow.name} v${workflow.version}`
              : 'No general generation workflow is enabled'}
          </p>

          <label className="field">
            <span>Prompt</span>
            <textarea
              className="form-textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the image to generate…"
            />
          </label>

          <div className="field">
            <span>Aspect ratio</span>
            <div className="preset-chips">
              {SIZE_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`preset-chip ${sizeId === p.id ? 'active' : ''}`}
                  onClick={() => applyPreset(p.id)}
                >
                  {p.label}
                </button>
              ))}
              <span
                className={`preset-chip ${sizeId === 'custom' ? 'active' : ''}`}
              >
                Custom
              </span>
            </div>
            <div className="field-row">
              <label className="field">
                <span>Width</span>
                <input
                  value={widthText}
                  inputMode="numeric"
                  onChange={(e) => {
                    setWidthText(e.target.value)
                    setSizeId('custom')
                  }}
                />
              </label>
              <label className="field">
                <span>Height</span>
                <input
                  value={heightText}
                  inputMode="numeric"
                  onChange={(e) => {
                    setHeightText(e.target.value)
                    setSizeId('custom')
                  }}
                />
              </label>
            </div>
          </div>

          <details className="advanced">
            <summary>Advanced</summary>
            <div className="advanced-body">
              <label className="field">
                <span>Negative prompt</span>
                <input
                  value={negative}
                  onChange={(e) => setNegative(e.target.value)}
                  placeholder="What to avoid (optional)"
                />
              </label>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={randomSeed}
                  onChange={(e) => setRandomSeed(e.target.checked)}
                />
                Random seed
              </label>
              <label className={`field ${randomSeed ? 'field-disabled' : ''}`}>
                <span>Seed</span>
                <input
                  value={seedText}
                  inputMode="numeric"
                  disabled={randomSeed}
                  onChange={(e) => setSeedText(e.target.value)}
                  placeholder="random"
                />
              </label>
              <div className="field-row">
                <label className="field">
                  <span>Steps</span>
                  <input
                    value={stepsText}
                    inputMode="numeric"
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>CFG</span>
                  <input
                    value={cfgText}
                    inputMode="decimal"
                    onChange={(e) => setCfgText(e.target.value)}
                  />
                </label>
              </div>
            </div>
          </details>

          <button
            type="button"
            className="btn"
            disabled={!workflow || !prompt.trim() || submitting}
            onClick={handleGenerate}
          >
            {submitting ? 'Submitting…' : 'Generate'}
          </button>
          {!workflow && (
            <p className="form-error">
              Enable the general generation workflow in Workflow Management.
            </p>
          )}
          {formError && <p className="form-error">{formError}</p>}
        </section>

        <section aria-label="Results">
          {activeJobs.length > 0 && (
            <div className="active-jobs">
              {activeJobs.map((job) => (
                <div
                  key={job.client_id}
                  role="button"
                  tabIndex={0}
                  className={`active-job ${
                    selectedClientId === job.client_id ? 'selected' : ''
                  }`}
                  onClick={() => setSelectedClientId(job.client_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') setSelectedClientId(job.client_id)
                  }}
                >
                  <div className="active-job-top">
                    <span className="active-job-status">{job.status}</span>
                    <span className="active-job-prompt">
                      {job.prompt || job.workflow_name}
                    </span>
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
                  </div>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${Math.round(job.progress * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {viewerJob ? (
            <JobResultViewer
              job={viewerJob}
              original={null}
              onPrev={goPrev}
              onNext={goNext}
              canPrev={canPrev}
              canNext={canNext}
               onCancel={
                 !TERMINAL_STATUSES.includes(viewerJob.status)
                   ? handleCancel
                   : undefined
               }
              onDeleteOutput={
                viewerJob.status === 'completed' ? requestDelete : undefined
              }
              onMoveOutput={
                viewerJob.status === 'completed' ? requestMove : undefined
              }
              onAddToGallery={
                viewerJob.status === 'completed' ? requestAdd : undefined
              }
            />
          ) : (
            <div className="gen-empty">
              <div className="placeholder-glyph">◈</div>
              <p>No results yet — generate your first image.</p>
            </div>
          )}

          {results.length > 0 && (
            <>
              <h2 className="results-title">Results</h2>
              <JobGallery
                jobs={results}
                selectedClientId={viewerJob?.client_id}
                onSelect={setSelectedClientId}
                onDelete={requestDelete}
                onMove={requestMove}
                onAddToGallery={requestAdd}
              />
            </>
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
