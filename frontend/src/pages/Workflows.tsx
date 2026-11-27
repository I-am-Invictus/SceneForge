import { useCallback, useEffect, useMemo, useState } from 'react'
import { Dialog } from '../components/Dialog'
import { listAssets } from '../services/assets'
import { getJob } from '../services/jobs'
import {
  activateVersion,
  getTemplate,
  getWorkflow,
  inspectVersion,
  listVersions,
  listWorkflows,
  patchWorkflow,
  saveMappings,
  testWorkflow,
  uploadVersion,
  uploadWorkflow,
  validateVersion,
} from '../services/workflows'
import { TERMINAL_STATUSES, type Job, type Workflow } from '../types/jobs'
import {
  CATEGORIES,
  CATEGORY_LABEL,
  INPUT_TYPES,
  type InputMappingRaw,
  type InputType,
  type StoredInput,
  type WorkflowInspection,
  type WorkflowReport,
  type WorkflowTestResult,
  type WorkflowValidationResult,
  type WorkflowVersion,
} from '../types/workflows'
import type { Asset } from '../types/assets'

const POLL_INTERVAL_MS = 2500

const CATEGORY_BADGE: Record<string, string> = {
  general_generation: 'cat-gen',
  image_modification: 'cat-mod',
  character_swap: 'cat-swap',
}

function parseWorkflowJson(text: string): Record<string, unknown> {
  const data = JSON.parse(text)
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    throw new Error('Workflow JSON must be an object mapping node id → node')
  }
  return data as Record<string, unknown>
}

export function Workflows() {
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showUpload, setShowUpload] = useState(false)

  const load = useCallback(async () => {
    try {
      setWorkflows(await listWorkflows())
      setLoadError(null)
    } catch (e) {
      setLoadError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (selectedId) {
    return (
      <WorkflowDetail
        id={selectedId}
        onBack={() => setSelectedId(null)}
        onSaved={() => void load()}
      />
    )
  }

  return (
    <div className="page">
      <div className="wf-topbar">
        <h1 className="wf-title">Workflow Management</h1>
        <button className="btn" onClick={() => setShowUpload(true)}>
          Upload workflow
        </button>
      </div>
      <p className="wf-sub">
        Register, inspect, map, validate, test, and version ComfyUI
        API-format workflows. Uploaded workflows and every version persist in
        storage and survive deploys.
      </p>
      {loadError && <div className="test-result off">{loadError}</div>}
      {workflows === null ? (
        <p className="dim">Loading…</p>
      ) : (
        <div className="wf-cards">
          {workflows.map((w) => (
            <button
              key={w.id}
              type="button"
              className="wf-card"
              onClick={() => setSelectedId(w.id)}
            >
              <div className="wf-card-top">
                <span className={`wf-badge ${CATEGORY_BADGE[w.category] ?? ''}`}>
                  {CATEGORY_LABEL[w.category] ?? w.category}
                </span>
                <span className={w.enabled ? 'wf-pill on' : 'wf-pill'}>
                  {w.enabled ? 'enabled' : 'disabled'}
                </span>
              </div>
              <div className="wf-card-name">{w.name}</div>
              <div className="wf-card-id">
                {w.id} · v{w.active_version ?? w.version}
              </div>
              {w.description && <div className="wf-card-desc">{w.description}</div>}
            </button>
          ))}
        </div>
      )}
      {showUpload && (
        <UploadDialog
          existingIds={workflows?.map((w) => w.id) ?? []}
          onClose={() => setShowUpload(false)}
          onUploaded={() => {
            setShowUpload(false)
            void load()
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------

function WorkflowDetail({
  id,
  onBack,
  onSaved,
}: {
  id: string
  onBack: () => void
  onSaved: () => void
}) {
  const [meta, setMeta] = useState<Workflow | null>(null)
  const [versions, setVersions] = useState<WorkflowVersion[] | null>(null)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [inspection, setInspection] = useState<WorkflowInspection | null>(null)
  const [validation, setValidation] = useState<WorkflowValidationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showNewVersion, setShowNewVersion] = useState(false)
  const [showEdit, setShowEdit] = useState(false)

  const reload = useCallback(async () => {
    const [m, vs] = await Promise.all([getWorkflow(id), listVersions(id)])
    setMeta(m)
    setVersions(vs)
    return { m, vs }
  }, [id])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { m, vs } = await reload()
        if (cancelled) return
        const active =
          vs.find((v) => v.is_active)?.version ?? m.active_version ?? m.version
        setSelectedVersion(active)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [reload])

  useEffect(() => {
    if (selectedVersion == null) return
    let cancelled = false
    setInspection(null)
    setValidation(null)
    inspectVersion(id, selectedVersion)
      .then((ins) => {
        if (!cancelled) setInspection(ins)
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [id, selectedVersion])

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function toggleEnabled() {
    if (!meta) return
    await withBusy(async () => {
      const next = await patchWorkflow(id, { enabled: !meta.enabled })
      setMeta(next)
      onSaved()
      setNotice(next.enabled ? 'Workflow enabled.' : 'Workflow disabled.')
    })
  }

  async function activate(v: number) {
    await withBusy(async () => {
      await activateVersion(id, v)
      setSelectedVersion(v)
      const { m } = await reload()
      void m
      onSaved()
      setNotice(`Active version set to v${v}.`)
    })
  }

  async function runValidate() {
    if (selectedVersion == null) return
    await withBusy(async () => {
      setValidation(await validateVersion(id, selectedVersion))
    })
  }

  return (
    <div className="page">
      <button className="btn secondary back-btn" onClick={onBack}>
        ← All workflows
      </button>

      <div className="wf-topbar">
        <div>
          <h1 className="wf-title">{meta?.name ?? id}</h1>
          <div className="wf-meta-row">
            <span className={`wf-badge ${CATEGORY_BADGE[meta?.category ?? ''] ?? ''}`}>
              {meta ? CATEGORY_LABEL[meta.category] ?? meta.category : ''}
            </span>
            <code className="wf-id">{id}</code>
            <span className={meta?.enabled ? 'wf-pill on' : 'wf-pill'}>
              {meta?.enabled ? 'enabled' : 'disabled'}
            </span>
          </div>
        </div>
        <div className="wf-actions">
          <button className="btn secondary" onClick={() => setShowEdit(true)}>
            Edit details
          </button>
          <button
            className="btn secondary"
            disabled={busy}
            onClick={() => void toggleEnabled()}
          >
            {meta?.enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() => setShowNewVersion(true)}
          >
            New version
          </button>
        </div>
      </div>

      {error && <div className="test-result off">{error}</div>}
      {notice && <div className="test-result ok">{notice}</div>}

      <section className="wf-panel">
        <h2>Versions</h2>
        {!versions ? (
          <p className="dim">Loading versions…</p>
        ) : (
          <div className="wf-versions">
            {versions.map((v) => (
              <div
                key={v.version}
                className={`wf-version ${selectedVersion === v.version ? 'selected' : ''}`}
              >
                <button
                  type="button"
                  className="wf-version-pick"
                  onClick={() => setSelectedVersion(v.version)}
                >
                  v{v.version}
                  {v.is_active && <span className="wf-pill on active">active</span>}
                  <span className="wf-version-count">
                    {Object.keys(v.inputs).length} inputs ·{' '}
                    {Object.keys(v.outputs).length} outputs
                  </span>
                </button>
                {!v.is_active && (
                  <button
                    className="btn secondary small"
                    disabled={busy}
                    onClick={() => void activate(v.version)}
                  >
                    Set active
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {selectedVersion != null && (
        <>
          <section className="wf-panel">
            <h2>
              Node inspection — v{selectedVersion}
              {inspection && !inspection.object_info_available && (
                <span className="wf-note">
                  {' '}
                  (ComfyUI unreachable — types and dependencies not checked)
                </span>
              )}
            </h2>
            {inspection ? (
              <InspectionPanel report={inspection.report} />
            ) : (
              <p className="dim">Inspecting…</p>
            )}
          </section>

          <section className="wf-panel">
            <h2>
              Input / output mapping — v{selectedVersion}
            </h2>
            {inspection ? (
              <MappingEditor
                key={`${id}-${selectedVersion}`}
                workflowId={id}
                version={selectedVersion}
                report={inspection.report}
                initialInputs={inspection.inputs}
                initialOutputs={inspection.outputs}
                onSaved={() => {
                  setNotice('Mappings saved.')
                  void inspectVersion(id, selectedVersion).then(setInspection)
                  setValidation(null)
                }}
                onError={setError}
              />
            ) : (
              <p className="dim">Waiting for inspection…</p>
            )}
          </section>

          <section className="wf-panel">
            <div className="wf-row-actions">
              <h2>Validate &amp; test — v{selectedVersion}</h2>
              <div className="wf-actions">
                <button
                  className="btn secondary"
                  disabled={busy || !inspection}
                  onClick={() => void runValidate()}
                >
                  Validate
                </button>
              </div>
            </div>
            {validation && (
              <div
                className={`test-result ${
                  validation.ok ? 'ok' : 'off'
                } wf-validation`}
              >
                <div className="wf-val-head">
                  {validation.connectivity ? (
                    validation.connectivity.connected ? (
                      <span className="wf-pill on">
                        ComfyUI {validation.connectivity.version ?? 'reachable'}
                      </span>
                    ) : (
                      <span className="wf-pill">ComfyUI unreachable</span>
                    )
                  ) : null}
                  <strong>{validation.ok ? 'Eligible to run' : 'Has blocking errors'}</strong>
                </div>
                {validation.errors.length > 0 && (
                  <ul className="wf-issue-list">
                    {validation.errors.map((e) => (
                      <li key={e} className="err">
                        {e}
                      </li>
                    ))}
                  </ul>
                )}
                {validation.warnings.length > 0 && (
                  <>
                    <div className="wf-val-sub">Warnings</div>
                    <ul className="wf-issue-list">
                      {validation.warnings.map((w) => (
                        <li key={w} className="warn">
                          {w}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {validation.errors.length === 0 &&
                  validation.warnings.length === 0 && (
                    <p>No errors or warnings.</p>
                  )}
              </div>
            )}
            <div className="wf-test">
              {inspection ? (
                <TestPanel
                  workflowId={id}
                  version={selectedVersion}
                  inputs={inspection.inputs}
                />
              ) : (
                <p className="dim">Waiting for inspection…</p>
              )}
            </div>
          </section>
        </>
      )}

      {showNewVersion && inspection && (
        <NewVersionDialog
          workflowId={id}
          baseVersion={selectedVersion ?? 1}
          baseInputs={inspection.inputs}
          baseOutputs={inspection.outputs}
          onClose={() => setShowNewVersion(false)}
          onUploaded={async (newVersion) => {
            setShowNewVersion(false)
            setSelectedVersion(newVersion)
            const { m } = await reload()
            void m
            onSaved()
            setNotice(`Uploaded as v${newVersion} (now active).`)
          }}
        />
      )}

      {showEdit && meta && (
        <EditDetailsDialog
          workflowId={id}
          name={meta.name}
          description={meta.description}
          onClose={() => setShowEdit(false)}
          onSaved={async (m) => {
            setMeta(m)
            setShowEdit(false)
            onSaved()
            setNotice('Details updated.')
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inspection
// ---------------------------------------------------------------------------

function InspectionPanel({ report }: { report: WorkflowReport }) {
  return (
    <div className="wf-inspect">
      <div className="wf-inspect-summary">
        <SummaryChip label="nodes" value={report.node_count} />
        <SummaryChip label="image loaders" value={report.image_loaders.length} />
        <SummaryChip label="output nodes" value={report.output_nodes.length} />
        <SummaryChip
          label="missing classes"
          value={report.missing_classes.length}
          tone={report.missing_classes.length ? 'warn' : undefined}
        />
        <SummaryChip
          label="missing models"
          value={report.referenced_models.filter((m) => !m.found).length}
          tone={
            report.referenced_models.some((m) => !m.found) ? 'warn' : undefined
          }
        />
      </div>

      {report.missing_classes.length > 0 && (
        <div className="test-result off">
          Missing custom node classes (install the plugin or fix the workflow):{' '}
          {report.missing_classes.join(', ')}
        </div>
      )}

      <div className="wf-inspect-cols">
        <div>
          <h3>Nodes</h3>
          <div className="wf-node-list">
            {report.nodes.map((n) => (
              <div key={n.id} className={`wf-node ${n.present ? '' : 'missing'}`}>
                <div className="wf-node-head">
                  <code>{n.id}</code>
                  <span className="wf-node-class">{n.class_type}</span>
                  {!n.present && <span className="wf-pill">missing</span>}
                  {n.is_image_loader && (
                    <span className="wf-pill img">image loader</span>
                  )}
                  {report.output_nodes.includes(n.id) && (
                    <span className="wf-pill out">output</span>
                  )}
                </div>
                <div className="wf-node-inputs">
                  {n.inputs.map((inp) => (
                    <span
                      key={inp.name}
                      className={`wf-node-input ${inp.is_link ? 'link' : ''}`}
                      title={
                        inp.types ? `types: ${inp.types.join('|')}` : undefined
                      }
                    >
                      {inp.name}
                      {inp.is_link ? ' ⤴' : ` = ${JSON.stringify(inp.value)}`}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="wf-inspect-side">
          <h3>Referenced models</h3>
          {report.referenced_models.length === 0 ? (
            <p className="dim">No model loaders detected.</p>
          ) : (
            <ul className="wf-model-list">
              {report.referenced_models.map((m, i) => (
                <li key={`${m.node_id}-${m.field}-${i}`} className={m.found ? '' : 'missing'}>
                  <code>{m.value}</code>
                  <span className="wf-model-loc">
                    node {m.node_id} · {m.field}
                  </span>
                  <span className={m.found ? 'wf-pill on' : 'wf-pill'}>
                    {m.found ? 'found' : 'missing'}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <h3>Hints (for mapping)</h3>
          <ul className="wf-hints">
            <HintRow label="Text inputs" items={report.text_inputs} />
            <HintRow label="Seed inputs" items={report.seed_inputs} />
            <HintRow label="Dimensions" items={report.dimension_inputs} />
            <HintRow label="Numbers" items={report.numeric_inputs} />
            <HintRow label="Booleans" items={report.boolean_inputs} />
            <HintRow label="Dropdowns" items={report.combo_inputs} />
          </ul>

          <h3>Custom classes</h3>
          <div className="wf-chip-wrap">
            {report.custom_classes.map((c) => (
              <span key={c} className="wf-chip">
                {c}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SummaryChip({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'warn'
}) {
  return (
    <div className={`wf-chip-stat ${tone ?? ''}`}>
      <span className="wf-chip-stat-n">{value}</span>
      <span className="wf-chip-stat-l">{label}</span>
    </div>
  )
}

function HintRow({
  label,
  items,
}: {
  label: string
  items: { node_id: string; field: string }[]
}) {
  return (
    <li>
      <span className="wf-hint-label">{label}</span>
      <span className="wf-hint-items">
        {items.length === 0
          ? '—'
          : items.map((i) => `${i.node_id}.${i.field}`).join(', ')}
      </span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Mapping editor
// ---------------------------------------------------------------------------

interface InputRow {
  name: string
  node_id: string
  input_name: string
  type: InputType
  required: boolean
  default: string
}

interface OutputRow {
  name: string
  node_id: string
  output_type: string
}

function rowsFromInputs(inputs: Record<string, StoredInput>): InputRow[] {
  return Object.entries(inputs).map(([name, m]) => ({
    name,
    node_id: m.node_id,
    input_name: m.input_name,
    type: (m.type as InputType) || 'text',
    required: m.required,
    default: m.default == null ? '' : String(m.default),
  }))
}

function rowsFromOutputs(
  outputs: Record<string, { node_id: string; output_type: string }[]>,
): OutputRow[] {
  const rows: OutputRow[] = []
  for (const [name, refs] of Object.entries(outputs)) {
    for (const r of refs) {
      rows.push({ name, node_id: r.node_id, output_type: r.output_type || 'images' })
    }
  }
  return rows
}

function MappingEditor({
  workflowId,
  version,
  report,
  initialInputs,
  initialOutputs,
  onSaved,
  onError,
}: {
  workflowId: string
  version: number
  report: WorkflowReport
  initialInputs: Record<string, StoredInput>
  initialOutputs: Record<string, { node_id: string; output_type: string }[]>
  onSaved: () => void
  onError: (msg: string | null) => void
}) {
  const [inputRows, setInputRows] = useState<InputRow[]>(() =>
    rowsFromInputs(initialInputs),
  )
  const [outputRows, setOutputRows] = useState<OutputRow[]>(() =>
    rowsFromOutputs(initialOutputs),
  )
  const [saving, setSaving] = useState(false)

  const nodeOptions = report.nodes
  const inputNamesFor = useCallback(
    (nodeId: string) =>
      report.nodes.find((n) => n.id === nodeId)?.inputs.map((i) => i.name) ?? [],
    [report],
  )

  function patchInput(idx: number, patch: Partial<InputRow>) {
    setInputRows((rows) =>
      rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)),
    )
  }
  function patchOutput(idx: number, patch: Partial<OutputRow>) {
    setOutputRows((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }

  async function handleSave() {
    setSaving(true)
    onError(null)
    try {
      const inputs: Record<string, InputMappingRaw> = {}
      for (const r of inputRows) {
        const name = r.name.trim()
        if (!name) continue
        inputs[name] = {
          node_id: r.node_id,
          input_name: r.input_name,
          type: r.type,
          required: r.required,
          default: parseDefault(r.type, r.default),
        }
      }
      const outputs: Record<string, { node_id: string; output_type: string }[]> = {}
      for (const r of outputRows) {
        const name = r.name.trim()
        if (!name || !r.node_id) continue
        const key = name
        outputs[key] = [
          ...(outputs[key] ?? []),
          { node_id: r.node_id, output_type: r.output_type || 'images' },
        ]
      }
      await saveMappings(workflowId, version, { inputs, outputs })
      onSaved()
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="wf-mapping">
      <div>
        <div className="wf-map-head">
          <h3>Inputs</h3>
          <button
            className="btn secondary small"
            onClick={() =>
              setInputRows((rows) => [
                ...rows,
                {
                  name: '',
                  node_id: nodeOptions[0]?.id ?? '',
                  input_name: '',
                  type: 'text',
                  required: false,
                  default: '',
                },
              ])
            }
          >
            + Add input
          </button>
        </div>
        {inputRows.length === 0 && (
          <p className="dim">No inputs mapped yet.</p>
        )}
        <div className="wf-map-table">
          <div className="wf-map-headrow">
            <span>Name</span>
            <span>Type</span>
            <span>Node</span>
            <span>Field</span>
            <span>Default</span>
            <span>Req</span>
            <span />
          </div>
          {inputRows.map((row, idx) => (
            <div className="wf-map-row" key={idx}>
              <input
                value={row.name}
                placeholder="input_name"
                onChange={(e) => patchInput(idx, { name: e.target.value })}
              />
              <select
                value={row.type}
                onChange={(e) => patchInput(idx, { type: e.target.value as InputType })}
              >
                {INPUT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <select
                value={row.node_id}
                onChange={(e) =>
                  patchInput(idx, { node_id: e.target.value, input_name: '' })
                }
              >
                {nodeOptions.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.id} · {n.class_type}
                  </option>
                ))}
              </select>
              <select
                value={row.input_name}
                onChange={(e) => patchInput(idx, { input_name: e.target.value })}
              >
                <option value="">—</option>
                {inputNamesFor(row.node_id).map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <input
                value={row.default}
                placeholder="default"
                onChange={(e) => patchInput(idx, { default: e.target.value })}
              />
              <label className="wf-req">
                <input
                  type="checkbox"
                  checked={row.required}
                  onChange={(e) => patchInput(idx, { required: e.target.checked })}
                />
              </label>
              <button
                className="icon-btn"
                aria-label="Remove input"
                onClick={() =>
                  setInputRows((rows) => rows.filter((_, i) => i !== idx))
                }
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="wf-map-head">
          <h3>Outputs</h3>
          <button
            className="btn secondary small"
            onClick={() =>
              setOutputRows((rows) => [
                ...rows,
                {
                  name: 'images',
                  node_id: report.output_nodes[0] ?? nodeOptions[0]?.id ?? '',
                  output_type: 'images',
                },
              ])
            }
          >
            + Add output
          </button>
        </div>
        {outputRows.length === 0 && (
          <p className="dim">No outputs mapped — the workflow will return nothing.</p>
        )}
        <div className="wf-map-table">
          <div className="wf-map-headrow out">
            <span>Name</span>
            <span>Node</span>
            <span>Type</span>
            <span />
          </div>
          {outputRows.map((row, idx) => (
            <div className="wf-map-row out" key={idx}>
              <input
                value={row.name}
                onChange={(e) => patchOutput(idx, { name: e.target.value })}
              />
              <select
                value={row.node_id}
                onChange={(e) => patchOutput(idx, { node_id: e.target.value })}
              >
                {nodeOptions.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.id}
                    {report.output_nodes.includes(n.id) ? ' ⏚' : ''} · {n.class_type}
                  </option>
                ))}
              </select>
              <input
                value={row.output_type}
                onChange={(e) =>
                  patchOutput(idx, { output_type: e.target.value })
                }
              />
              <button
                className="icon-btn"
                aria-label="Remove output"
                onClick={() =>
                  setOutputRows((rows) => rows.filter((_, i) => i !== idx))
                }
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="wf-map-save">
        <button className="btn" disabled={saving} onClick={() => void handleSave()}>
          {saving ? 'Saving…' : 'Save mappings'}
        </button>
      </div>
    </div>
  )
}

function parseDefault(type: InputType, raw: string): unknown {
  const text = raw.trim()
  if (text === '') return type === 'boolean' ? false : undefined
  if (type === 'boolean') return text.toLowerCase() === 'true'
  if (type === 'number' || type === 'seed' || type === 'width' || type === 'height') {
    const n = Number(text)
    return Number.isFinite(n) ? n : undefined
  }
  return text
}

// ---------------------------------------------------------------------------
// Test panel
// ---------------------------------------------------------------------------

function TestPanel({
  workflowId,
  version,
  inputs,
}: {
  workflowId: string
  version: number
  inputs: Record<string, StoredInput>
}) {
  const [assets, setAssets] = useState<Asset[] | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [bools, setBools] = useState<Record<string, boolean>>({})
  const [images, setImages] = useState<Record<string, number>>({})
  const [result, setResult] = useState<WorkflowTestResult | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const needsImages = Object.values(inputs).some((i) => i.type === 'image')

  useEffect(() => {
    if (!needsImages) return
    let cancelled = false
    Promise.all([listAssets('scene'), listAssets('character')])
      .then(([scenes, characters]) => {
        if (!cancelled) setAssets([...scenes, ...characters])
      })
      .catch(() => {
        if (!cancelled) setAssets([])
      })
    return () => {
      cancelled = true
    }
  }, [needsImages])

  useEffect(() => {
    const v: Record<string, string> = {}
    const b: Record<string, boolean> = {}
    for (const [name, inp] of Object.entries(inputs)) {
      if (inp.type === 'boolean') b[name] = inp.required ? true : false
      else if (inp.default != null && inp.type !== 'image')
        v[name] = String(inp.default)
    }
    setValues(v)
    setBools(b)
    setImages({})
    setResult(null)
    setJob(null)
    setError(null)
  }, [inputs])

  const imageOptions = useMemo(() => {
    const opts: { fileId: number; label: string }[] = []
    for (const asset of assets ?? []) {
      const file = asset.files.find((f) => f.is_default) ?? asset.files[0]
      if (!file) continue
      opts.push({
        fileId: file.id,
        label: `${asset.kind === 'scene' ? 'Scene' : 'Character'}: ${asset.name}`,
      })
    }
    return opts
  }, [assets])

  useEffect(() => {
    if (!job || TERMINAL_STATUSES.includes(job.status)) return
    let stopped = false
    const timer = setInterval(async () => {
      try {
        const fresh = await getJob(job.client_id)
        if (!stopped) setJob(fresh)
      } catch {
        // keep polling
      }
    }, POLL_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [job])

  function buildInputs(): Record<string, unknown> {
    const out: Record<string, unknown> = {}
    for (const [name, inp] of Object.entries(inputs)) {
      if (inp.type === 'image') {
        const fid = images[name]
        if (fid != null) out[name] = { asset_file_id: fid }
        else if (inp.required) throw new Error(`Pick an image for “${name}”.`)
      } else if (inp.type === 'boolean') {
        out[name] = bools[name] ? 'true' : 'false'
      } else if (
        inp.type === 'number' ||
        inp.type === 'seed' ||
        inp.type === 'width' ||
        inp.type === 'height'
      ) {
        const raw = (values[name] ?? '').trim()
        if (raw === '') continue
        out[name] = Number(raw)
      } else {
        const raw = (values[name] ?? '').trim()
        if (raw === '') {
          if (inp.required) throw new Error(`Fill in “${name}”.`)
          continue
        }
        out[name] = raw
      }
    }
    return out
  }

  async function runTest() {
    setRunning(true)
    setError(null)
    setResult(null)
    setJob(null)
    try {
      const testInputs = buildInputs()
      const res = await testWorkflow(workflowId, {
        version,
        test_inputs: testInputs,
      })
      setResult(res)
      if (res.job_client_id) {
        const initial = await getJob(res.job_client_id)
        setJob(initial)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const jobTerminal = job ? TERMINAL_STATUSES.includes(job.status) : false

  return (
    <div className="wf-testbody">
      <p className="wf-test-sub">
        Runs a real generation job with the mapping above. Success is only
        reported once the job completes with outputs.
      </p>
      {Object.keys(inputs).length === 0 ? (
        <p className="dim">No inputs mapped yet — save a mapping first.</p>
      ) : (
        <div className="wf-test-form">
          {Object.entries(inputs).map(([name, inp]) => (
            <TestField
              key={name}
              name={name}
              type={inp.type}
              required={inp.required}
              value={values[name] ?? ''}
              checked={bools[name] ?? false}
              imageId={images[name]}
              imageOptions={imageOptions}
              onChange={(v) => setValues((s) => ({ ...s, [name]: v }))}
              onCheck={(c) => setBools((s) => ({ ...s, [name]: c }))}
              onImage={(fid) => setImages((s) => ({ ...s, [name]: fid }))}
            />
          ))}
        </div>
      )}

      <button
        className="btn"
        disabled={running || Object.keys(inputs).length === 0}
        onClick={() => void runTest()}
      >
        {running || (job && !jobTerminal) ? 'Running…' : 'Run test generation'}
      </button>

      {error && <div className="test-result off">{error}</div>}

      {result && (
        <div
          className={`test-result ${result.ok ? 'ok' : 'off'} wf-test-result`}
        >
          {result.connectivity && !result.connectivity.connected && (
            <p>ComfyUI unreachable.</p>
          )}
          {result.issues.map((i) => (
            <p key={i} className="err">
              {i}
            </p>
          ))}
          {result.warnings.map((w) => (
            <p key={w} className="warn">
              {w}
            </p>
          ))}
          {result.ok && !result.submitted && (
            <p>Validation passed but the test job was not submitted.</p>
          )}
        </div>
      )}

      {job && (
        <div
          className={`test-result ${
            job.status === 'completed'
              ? 'ok'
              : job.status === 'queued' || job.status === 'running'
                ? ''
                : 'off'
          } wf-job-result`}
        >
          <div className="wf-job-top">
            <span className={`wf-pill ${job.status === 'completed' ? 'on' : ''}`}>
              {job.status}
            </span>
            <span>{job.prompt || job.workflow_name}</span>
          </div>
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${Math.round(job.progress * 100)}%` }}
            />
          </div>
          {job.status === 'completed' && (
            <p>
              ✓ Test succeeded — {job.outputs.length} output
              {job.outputs.length === 1 ? '' : 's'} retrieved.
            </p>
          )}
          {job.status === 'failed' && <p className="err">{job.error}</p>}
          {job.status === 'interrupted' && <p>Job was interrupted.</p>}
        </div>
      )}
    </div>
  )
}

function TestField({
  name,
  type,
  required,
  value,
  checked,
  imageId,
  imageOptions,
  onChange,
  onCheck,
  onImage,
}: {
  name: string
  type: InputType
  required: boolean
  value: string
  checked: boolean
  imageId?: number
  imageOptions: { fileId: number; label: string }[]
  onChange: (v: string) => void
  onCheck: (c: boolean) => void
  onImage: (fileId: number) => void
}) {
  const label = (
    <span>
      {name}
      {required && <span className="wf-req-asterisk"> *</span>}
    </span>
  )
  if (type === 'boolean') {
    return (
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
        />
        {name}
        {required && <span className="wf-req-asterisk"> *</span>}
      </label>
    )
  }
  if (type === 'image') {
    return (
      <label className="field">
        {label}
        <select
          value={imageId ?? ''}
          onChange={(e) => onImage(Number(e.target.value))}
        >
          <option value="">— select image —</option>
          {imageOptions.map((o) => (
            <option key={o.fileId} value={o.fileId}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    )
  }
  if (
    type === 'number' ||
    type === 'seed' ||
    type === 'width' ||
    type === 'height'
  ) {
    return (
      <label className="field">
        {label}
        <input
          value={value}
          inputMode="numeric"
          placeholder={type === 'seed' ? 'random' : 'default'}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    )
  }
  if (type === 'text') {
    return (
      <label className="field">
        {label}
        <textarea
          className="form-textarea"
          value={value}
          placeholder="…"
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    )
  }
  return (
    <label className="field">
      {label}
      <input
        value={value}
        placeholder="…"
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

// ---------------------------------------------------------------------------
// Upload / new-version / edit dialogs
// ---------------------------------------------------------------------------

function UploadDialog({
  existingIds,
  onClose,
  onUploaded,
}: {
  existingIds: string[]
  onClose: () => void
  onUploaded: () => void
}) {
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState<string>('general_generation')
  const [description, setDescription] = useState('')
  const [workflowText, setWorkflowText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const workflow = parseWorkflowJson(workflowText)
      await uploadWorkflow({
        id: id.trim(),
        name: name.trim() || id.trim(),
        category,
        description,
        workflow,
        inputs: {},
        outputs: {},
      })
      onUploaded()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog title="Upload workflow" onClose={onClose} wide>
      <div className="dialog-body">
        <p className="dim">
          Paste a ComfyUI <strong>API-format</strong> workflow (the prompt
          JSON: node id → node). Mappings are configured after upload.
        </p>
        <div className="field-row">
          <label className="field">
            <span>Workflow id</span>
            <input
              value={id}
              placeholder="my_workflow_v1"
              onChange={(e) => setId(e.target.value.toLowerCase())}
            />
          </label>
          <label className="field">
            <span>Name</span>
            <input
              value={name}
              placeholder="My Workflow"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        </div>
        <div className="field-row">
          <label className="field">
            <span>Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Description</span>
            <input
              value={description}
              placeholder="optional"
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </div>
        <label className="field">
          <span>Workflow JSON</span>
          <textarea
            className="wf-json"
            value={workflowText}
            placeholder='{"3": {"class_type": "KSampler", "inputs": {...}}, ...}'
            onChange={(e) => setWorkflowText(e.target.value)}
          />
        </label>
        {id && existingIds.includes(id.trim()) && (
          <p className="form-error">
            That id already exists — open it and add a new version instead.
          </p>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="dialog-actions">
          <button className="btn secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn"
            disabled={busy || !id.trim() || !workflowText.trim()}
            onClick={() => void submit()}
          >
            {busy ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </Dialog>
  )
}

function NewVersionDialog({
  workflowId,
  baseVersion,
  baseInputs,
  baseOutputs,
  onClose,
  onUploaded,
}: {
  workflowId: string
  baseVersion: number
  baseInputs: Record<string, StoredInput>
  baseOutputs: Record<string, { node_id: string; output_type: string }[]>
  onClose: () => void
  onUploaded: (newVersion: number) => void
}) {
  const [workflowText, setWorkflowText] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getTemplate(workflowId, baseVersion)
      .then((tpl) => {
        if (!cancelled) {
          setWorkflowText(JSON.stringify(tpl, null, 2))
          setLoaded(true)
        }
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [workflowId, baseVersion])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const workflow = parseWorkflowJson(workflowText)
      const inputs: Record<string, InputMappingRaw> = Object.fromEntries(
        Object.entries(baseInputs).map(([k, v]) => [k, v]),
      )
      const outputs = baseOutputs
      const created = await uploadVersion(workflowId, { workflow, inputs, outputs })
      onUploaded(created.version)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      title={`New version for ${workflowId}`}
      onClose={onClose}
      wide
    >
      <div className="dialog-body">
        <p className="dim">
          Prefilled with v{baseVersion}'s template and mappings. Edit the
          JSON, then save as a new immutable version (it becomes active).
        </p>
        {!loaded && !error && <p className="dim">Loading template…</p>}
        {loaded && (
          <label className="field">
            <span>Workflow JSON</span>
            <textarea
              className="wf-json tall"
              value={workflowText}
              onChange={(e) => setWorkflowText(e.target.value)}
            />
          </label>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="dialog-actions">
          <button className="btn secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn"
            disabled={busy || !loaded}
            onClick={() => void submit()}
          >
            {busy ? 'Saving…' : 'Save new version'}
          </button>
        </div>
      </div>
    </Dialog>
  )
}

function EditDetailsDialog({
  workflowId,
  name,
  description,
  onClose,
  onSaved,
}: {
  workflowId: string
  name: string
  description: string
  onClose: () => void
  onSaved: (m: Workflow) => void
}) {
  const [nameV, setNameV] = useState(name)
  const [descV, setDescV] = useState(description)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const m = await patchWorkflow(workflowId, {
        name: nameV.trim(),
        description: descV,
      })
      onSaved(m)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog title="Edit workflow details" onClose={onClose}>
      <div className="dialog-body">
        <label className="field">
          <span>Name</span>
          <input value={nameV} onChange={(e) => setNameV(e.target.value)} />
        </label>
        <label className="field">
          <span>Description</span>
          <textarea
            className="form-textarea"
            value={descV}
            onChange={(e) => setDescV(e.target.value)}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <div className="dialog-actions">
          <button className="btn secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn"
            disabled={busy || !nameV.trim()}
            onClick={() => void submit()}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Dialog>
  )
}
