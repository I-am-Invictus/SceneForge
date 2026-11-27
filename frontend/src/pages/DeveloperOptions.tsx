import { useState } from 'react'
import { ResetDataDialog } from '../components/ResetDataDialog'

export function DeveloperOptions() {
  const [showReset, setShowReset] = useState(false)

  return (
    <div className="page developer-page">
      <header className="page-header">
        <h1>Developer Options</h1>
      </header>
      <div className="developer-notice">
        <span className="developer-badge">Developer mode</span>
        <p>
          These tools are for personal testing and development only. They are
          separate from normal use and are hidden unless developer mode is
          enabled.
        </p>
      </div>

      <section className="settings-card danger-zone">
        <h2>Danger Zone</h2>
        <p className="settings-hint">
          Actions here make permanent, hard-to-reverse changes to your local
          SceneForge data.
        </p>
        <div className="dev-action">
          <div className="dev-action-text">
            <div className="dev-action-title">Reset Application Data</div>
            <div className="dev-action-desc">
              Return SceneForge to a completely empty first-run state. This
              permanently deletes all uploaded images, generated images,
              galleries, and history. Application settings and workflow
              configurations are preserved.
            </div>
          </div>
          <button className="btn danger" onClick={() => setShowReset(true)}>
            Reset…
          </button>
        </div>
      </section>

      {showReset && <ResetDataDialog onClose={() => setShowReset(false)} />}
    </div>
  )
}
