import { useState } from 'react'
import { Dialog } from './Dialog'
import { resetApplicationData } from '../services/developer'
import type { ResetReport } from '../types/developer'

const CONFIRM_WORD = 'RESET'

function summarize(counts: Record<string, number>): string {
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${k}=${n}`)
  return parts.length ? parts.join(', ') : 'none'
}

export function ResetDataDialog({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorReport, setErrorReport] = useState<ResetReport | null>(null)
  const [done, setDone] = useState(false)

  const canConfirm = text.trim() === CONFIRM_WORD && !busy

  const confirm = async () => {
    setBusy(true)
    setError(null)
    setErrorReport(null)
    try {
      const report = await resetApplicationData(CONFIRM_WORD)
      if (!report.ok) {
        throw new Error(report.error || 'Reset failed.')
      }
      setDone(true)
    } catch (err) {
      const e = err as Error & { report?: ResetReport }
      setError(e.message)
      if (e.report) setErrorReport(e.report)
      setBusy(false)
    }
  }

  const reload = () => window.location.replace('/')

  if (done) {
    return (
      <Dialog title="Reset complete" onClose={onClose}>
        <p className="dialog-message">
          Application data has been cleared. SceneForge is now in an empty
          first-run state. Application settings and workflow configurations were
          preserved.
        </p>
        <div className="dialog-actions">
          <button className="btn" onClick={reload}>
            Reload application
          </button>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog title="Reset Application Data" onClose={onClose} wide>
      <div className="reset-warn">
        <p>
          This <strong>permanently deletes</strong> all user-generated
          application data, including:
        </p>
        <ul>
          <li>Uploaded Scene and Character images and references</li>
          <li>Generated images and job outputs</li>
          <li>Thumbnails and derived image files</li>
          <li>Galleries, gallery memberships, and Starred associations</li>
          <li>Image-related history and associated records</li>
          <li>Temporary uploads and SceneForge-managed image copies</li>
        </ul>
        <p>
          Application settings, workflow configurations and versions, and the
          reference workflows are preserved. This action cannot be undone.
        </p>
      </div>

      {error && (
        <div className="form-error">
          <p>Reset failed: {error}</p>
          {errorReport && (
            <p className="reset-diag">
              Rows before: {summarize(errorReport.before)} · after:{' '}
              {summarize(errorReport.after)}
            </p>
          )}
        </div>
      )}

      <label className="field">
        <span>
          Type <code>RESET</code> to confirm
        </span>
        <input
          type="text"
          value={text}
          autoFocus
          onChange={(e) => setText(e.target.value)}
          placeholder="RESET"
          spellCheck={false}
          disabled={busy}
        />
      </label>

      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn danger" onClick={confirm} disabled={!canConfirm}>
          {busy ? 'Resetting…' : 'Permanently reset'}
        </button>
      </div>
    </Dialog>
  )
}
