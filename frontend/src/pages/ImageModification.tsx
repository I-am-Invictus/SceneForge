import { useCallback, useEffect, useState } from 'react'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { MoveToLibraryDialog } from '../components/MoveToLibraryDialog'
import type { CompareImage } from '../components/ImageComparison'
import { Icon } from '../components/icons'
import { JobGallery } from '../components/JobGallery'
import { JobResultViewer } from '../components/JobResultViewer'
import { SourceImagePicker } from '../components/SourceImagePicker'
import { listAssets } from '../services/assets'
import {
  cancelJob,
  deleteJobOutput,
  generate,
  getJob,
  listJobs,
  listWorkflows,
  moveJobOutput,
} from '../services/jobs'
import { TERMINAL_STATUSES, type Job, type Workflow } from '../types/jobs'
import type { Asset, AssetFile, AssetKind } from '../types/assets'

interface SourceSelection {
  asset: Asset
  file: AssetFile
}

// Both editing modes drive the same instruction-based edit workflow; the mode
// only shapes the prompt guidance, it is not a workflow input.
type EditMode = 'scene' | 'character'

const EDIT_MODES: Record<
  EditMode,
  { label: string; promptLabel: string; placeholder: string; hint: string }
> = {
  scene: {
    label: 'Scene',
    promptLabel: 'Scene prompt',
    placeholder:
      'e.g. Turn the sky into a warm sunset, add street lamps, and calm the water…',
    hint: 'Environment, background, objects, lighting, and composition.',
  },
  character: {
    label: 'Character',
    promptLabel: 'Character prompt',
    placeholder:
      'e.g. Change the jacket to a red leather coat and make the hair longer…',
    hint: 'Appearance, clothing, and pose of the person in the image.',
  },
}

const POLL_INTERVAL_MS = 2500

function roundTo8(value: number, minimum = 16, maximum = 2048): number {
  const rounded = Math.round(value / 8) * 8
  return Math.min(maximum, Math.max(minimum, rounded))
}

export function ImageModification() {
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [activeJobs, setActiveJobs] = useState<Job[]>([])
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Source images can come from either library (scenes for scene edits,
  // characters for character edits), so the original map spans both.
  const [sourceFiles, setSourceFiles] = useState<Map<number, AssetFile>>(
    new Map(),
  )

  const [source, setSource] = useState<SourceSelection | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [mode, setMode] = useState<EditMode>('scene')
  const [prompt, setPrompt] = useState('')
  const [negative, setNegative] = useState('')
  const [sizeMode, setSizeMode] = useState<'auto' | 'custom'>('auto')
  const [widthText, setWidthText] = useState('')
  const [heightText, setHeightText] = useState('')
  const [batchText, setBatchText] = useState('1')
  const [denoiseText, setDenoiseText] = useState('1')
  const [stepsText, setStepsText] = useState('4')
  const [randomSeed, setRandomSeed] = useState(true)
  const [seedText, setSeedText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [confirmDelete, setConfirmDelete] = useState<{
    clientId: string
    outputId: number
  } | null>(null)
  const [moveTarget, setMoveTarget] = useState<{
    clientId: string
    outputId: number
  } | null>(null)

  const workflow =
    workflows?.find(
      (w) => w.category === 'image_modification' && w.enabled,
    ) ?? null

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
    let cancelled = false
    ;(async () => {
      try {
        const wfs = await listWorkflows()
        if (cancelled) return
        setWorkflows(wfs)
        const mod = wfs.find(
          (w) => w.category === 'image_modification' && w.enabled,
        )
        if (mod) {
          const list = await listJobs({ workflow_id: mod.id, limit: 60 })
          if (!cancelled) setJobs(list)
        }
      } catch (e) {
        if (!cancelled) setLoadError((e as Error).message)
      }
    })()
    refreshSourceFiles()
    return () => {
      cancelled = true
    }
  }, [refreshSourceFiles])

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

  function originalFor(job: Job): CompareImage | null {
    const src = job.inputs.source_image
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

  async function handleGenerate() {
    if (!workflow || !source || submitting) return
    setSubmitting(true)
    setFormError(null)
    try {
      const batch = Number(batchText)
      if (!Number.isInteger(batch) || batch < 1 || batch > 8) {
        setFormError('Batch size must be a whole number between 1 and 8.')
        return
      }
      const denoise = Number(denoiseText)
      if (!Number.isFinite(denoise) || denoise < 0 || denoise > 1) {
        setFormError('Denoise must be between 0 and 1.')
        return
      }
      const steps = Number(stepsText)
      if (!Number.isFinite(steps) || steps < 1) {
        setFormError('Steps must be a positive number.')
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
        source_image: { asset_file_id: source.file.id },
        prompt: prompt.trim(),
        batch_size: batch,
        denoise,
        steps,
        seed,
      }
      if (negative.trim()) inputs.negative_prompt = negative.trim()
      if (sizeMode === 'custom') {
        const width = roundTo8(Number(widthText))
        const height = roundTo8(Number(heightText))
        if (!Number.isFinite(width) || !Number.isFinite(height)) {
          setFormError('Width and height must be numbers.')
          return
        }
        inputs.width = width
        inputs.height = height
      }
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
      setJobs((prev) => [
        fresh,
        ...prev.filter((j) => j.client_id !== clientId),
      ])
    } catch (e) {
      setFormError((e as Error).message)
    }
  }

  async function handleDeleteConfirmed() {
    if (!confirmDelete) return
    const { clientId, outputId } = confirmDelete
    const fresh = await deleteJobOutput(clientId, outputId)
    setJobs((prev) => [fresh, ...prev.filter((j) => j.client_id !== clientId)])
  }

  async function handleMoveConfirmed(folder: AssetKind) {
    if (!moveTarget) return
    const { clientId, outputId } = moveTarget
    const fresh = await moveJobOutput(clientId, outputId, folder)
    setJobs((prev) => [fresh, ...prev.filter((j) => j.client_id !== clientId)])
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
  const requestDelete = (clientId: string, outputId: number) => {
    setConfirmDelete({ clientId, outputId })
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Image Modification</h1>
      </header>

      {loadError && <div className="test-result off">{loadError}</div>}

      <div className="gen-layout">
        <section className="gen-form" aria-label="Modification settings">
          <h2>Modify an image</h2>
          <p className="gen-form-sub">
            {workflow
              ? `${workflow.name} v${workflow.version}`
              : 'No image modification workflow is enabled'}
          </p>

          <div className="field">
            <span>Source image</span>
            {source ? (
              <div className="source-card">
                <img
                  className="source-card-img"
                  src={source.file.original_url}
                  alt={source.file.display_name}
                />
                <div className="source-card-info">
                  <span className="source-card-name">{source.asset.name}</span>
                  <span className="source-card-meta">
                    {source.file.width}×{source.file.height}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => setPickerOpen(true)}
                >
                  Change
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="file-drop source-pick"
                onClick={() => setPickerOpen(true)}
              >
                <Icon name="scenes" size={16} />
                Choose or upload a source image
              </button>
            )}
          </div>

          <div className="field">
            <span>Editing mode</span>
            <div className="preset-chips">
              {(Object.keys(EDIT_MODES) as EditMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`preset-chip ${mode === m ? 'active' : ''}`}
                  onClick={() => setMode(m)}
                >
                  {EDIT_MODES[m].label}
                </button>
              ))}
            </div>
            <p className="mode-hint">{EDIT_MODES[mode].hint}</p>
          </div>

          <label className="field">
            <span>{EDIT_MODES[mode].promptLabel}</span>
            <textarea
              className="form-textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={EDIT_MODES[mode].placeholder}
            />
          </label>

          <details className="advanced" open>
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
              <div className="field">
                <span>Size</span>
                <div className="preset-chips">
                  <button
                    type="button"
                    className={`preset-chip ${sizeMode === 'auto' ? 'active' : ''}`}
                    onClick={() => setSizeMode('auto')}
                  >
                    Match source
                  </button>
                  <button
                    type="button"
                    className={`preset-chip ${sizeMode === 'custom' ? 'active' : ''}`}
                    onClick={() => setSizeMode('custom')}
                  >
                    Custom
                  </button>
                </div>
                {sizeMode === 'custom' && (
                  <div className="field-row">
                    <label className="field">
                      <span>Width</span>
                      <input
                        value={widthText}
                        inputMode="numeric"
                        onChange={(e) => setWidthText(e.target.value)}
                        placeholder="auto"
                      />
                    </label>
                    <label className="field">
                      <span>Height</span>
                      <input
                        value={heightText}
                        inputMode="numeric"
                        onChange={(e) => setHeightText(e.target.value)}
                        placeholder="auto"
                      />
                    </label>
                  </div>
                )}
              </div>
              <div className="field-row">
                <label className="field">
                  <span>Batch size</span>
                  <input
                    value={batchText}
                    inputMode="numeric"
                    onChange={(e) => setBatchText(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Denoise</span>
                  <input
                    value={denoiseText}
                    inputMode="decimal"
                    onChange={(e) => setDenoiseText(e.target.value)}
                  />
                </label>
              </div>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={randomSeed}
                  onChange={(e) => setRandomSeed(e.target.checked)}
                />
                Random seed
              </label>
              <div className="field-row">
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
                <label className="field">
                  <span>Steps</span>
                  <input
                    value={stepsText}
                    inputMode="numeric"
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </label>
              </div>
            </div>
          </details>

          <button
            type="button"
            className="btn"
            disabled={!workflow || !source || !prompt.trim() || submitting}
            onClick={handleGenerate}
          >
            {submitting ? 'Submitting…' : 'Modify image'}
          </button>
          {!workflow && (
            <p className="form-error">
              Enable the image modification workflow in Workflow Management.
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
              original={originalFor(viewerJob)}
              onPrev={goPrev}
              onNext={goNext}
              canPrev={canPrev}
              canNext={canNext}
              onCancel={
                viewerJob.status === 'queued' || viewerJob.status === 'running'
                  ? handleCancel
                  : undefined
              }
              onDeleteOutput={
                viewerJob.status === 'completed' ? requestDelete : undefined
              }
              onMoveOutput={
                viewerJob.status === 'completed'
                  ? (clientId, outputId) =>
                      setMoveTarget({ clientId, outputId })
                  : undefined
              }
            />
          ) : (
            <div className="gen-empty">
              <div className="placeholder-glyph">◈</div>
              <p>No results yet — choose a source image and describe a change.</p>
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
                onMove={(clientId, outputId) =>
                  setMoveTarget({ clientId, outputId })
                }
              />
            </>
          )}
        </section>
      </div>

      {pickerOpen && (
        <SourceImagePicker
          onClose={() => setPickerOpen(false)}
          onSelect={(asset, file) => {
            setSource({ asset, file })
            setPickerOpen(false)
          }}
          kind={mode}
          onAssetsChanged={refreshSourceFiles}
        />
      )}

      {moveTarget && (
        <MoveToLibraryDialog
          onMove={(folder) => handleMoveConfirmed(folder)}
          onClose={() => setMoveTarget(null)}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete generated image?"
          message="This permanently removes the selected generated image and its thumbnail. The source image and all other outputs are not affected."
          onConfirm={handleDeleteConfirmed}
          onClose={() => setConfirmDelete(null)}
        />
      )}
    </div>
  )
}
