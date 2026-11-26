import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api'
import type { AppSettings, ComfyuiStatus } from '../types'

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<ComfyuiStatus | null>(null)
  const [testing, setTesting] = useState(false)

  const load = useCallback(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s)
        setDraft(s)
        setLoadError(null)
      })
      .catch((err: Error) => setLoadError(err.message))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    if (!draft) return
    setSaving(true)
    setSaveMessage(null)
    try {
      const saved = await api.updateSettings(draft)
      setSettings(saved)
      setDraft(saved)
      setSaveMessage('Settings saved')
    } catch (err) {
      setSaveMessage(`Save failed: ${(err as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await api.comfyuiStatus())
    } catch (err) {
      setTestResult({
        connected: false,
        version: null,
        detail: (err as Error).message,
      })
    } finally {
      setTesting(false)
    }
  }

  if (loadError) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>Settings</h1>
        </header>
        <div className="placeholder-card">
          <p>Could not load settings: {loadError}</p>
        </div>
      </div>
    )
  }

  if (!settings || !draft) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>Settings</h1>
        </header>
        <div className="placeholder-card">
          <p>Loading…</p>
        </div>
      </div>
    )
  }

  const dirty =
    draft.comfyui_http_url !== settings.comfyui_http_url ||
    draft.comfyui_ws_url !== settings.comfyui_ws_url

  return (
    <div className="page">
      <header className="page-header">
        <h1>Settings</h1>
      </header>

      <section className="settings-card">
        <h2>ComfyUI Connection</h2>
        <p className="settings-hint">
          Backend-to-ComfyUI communication always uses these URLs on the host
          machine. Machine defaults come from the environment; values saved
          here override them.
        </p>

        <label className="field">
          <span>HTTP URL</span>
          <input
            type="text"
            value={draft.comfyui_http_url}
            onChange={(e) =>
              setDraft({ ...draft, comfyui_http_url: e.target.value })
            }
            placeholder="http://127.0.0.1:8188"
            spellCheck={false}
          />
        </label>

        <label className="field">
          <span>WebSocket URL</span>
          <input
            type="text"
            value={draft.comfyui_ws_url}
            onChange={(e) =>
              setDraft({ ...draft, comfyui_ws_url: e.target.value })
            }
            placeholder="ws://127.0.0.1:8188/ws"
            spellCheck={false}
          />
        </label>

        <div className="settings-actions">
          <button className="btn" onClick={save} disabled={saving || !dirty}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            className="btn secondary"
            onClick={testConnection}
            disabled={testing}
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
          {saveMessage && <span className="settings-message">{saveMessage}</span>}
        </div>

        {testResult && (
          <div className={`test-result ${testResult.connected ? 'ok' : 'off'}`}>
            {testResult.connected ? (
              <>
                Connected
                {testResult.version ? ` · ComfyUI v${testResult.version}` : ''}
              </>
            ) : (
              <>Disconnected{testResult.detail ? ` · ${testResult.detail}` : ''}</>
            )}
          </div>
        )}
      </section>

      <section className="settings-card">
        <h2>Storage</h2>
        <p className="settings-hint">
          Persistent data lives outside the application directory and survives
          updates and restarts.
        </p>
        <dl className="settings-dl">
          <dt>Data directory</dt>
          <dd>/var/lib/sceneforge</dd>
          <dt>Generated images</dt>
          <dd>/var/lib/sceneforge/generated</dd>
          <dt>Asset library</dt>
          <dd>/var/lib/sceneforge/assets</dd>
        </dl>
      </section>
    </div>
  )
}
