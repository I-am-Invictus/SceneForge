import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Icon, type IconName } from './icons'
import { ComfyuiBadge } from './ComfyuiBadge'
import { getDeveloperStatus } from '../services/developer'

interface NavItem {
  to: string
  label: string
  icon: IconName
}

const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Create',
    items: [
      { to: '/generate', label: 'General Generation', icon: 'generate' },
      { to: '/modify', label: 'Image Modification', icon: 'modify' },
      { to: '/swap', label: 'Character Swapping', icon: 'swap' },
      { to: '/queue', label: 'Queue', icon: 'queue' },
    ],
  },
  {
    title: 'Library',
    items: [
      { to: '/characters', label: 'Characters', icon: 'characters' },
      { to: '/scenes', label: 'Scenes', icon: 'scenes' },
      { to: '/galleries', label: 'Galleries', icon: 'galleries' },
      { to: '/starred', label: 'Starred Assets', icon: 'star' },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/history', label: 'Generation History', icon: 'history' },
      { to: '/workflows', label: 'Workflow Management', icon: 'workflows' },
      { to: '/settings', label: 'Settings', icon: 'settings' },
    ],
  },
]

export function Sidebar() {
  const [open, setOpen] = useState(false)
  const [devMode, setDevMode] = useState(false)

  useEffect(() => {
    getDeveloperStatus()
      .then((s) => setDevMode(s.dev_mode))
      .catch(() => setDevMode(false))
  }, [])

  return (
    <>
      <button
        className="nav-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle navigation"
      >
        <Icon name={open ? 'close' : 'menu'} />
      </button>

      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">S</div>
          <div className="brand-text">
            <span className="brand-name">SceneForge</span>
            <span className="brand-sub">Studio</span>
          </div>
        </div>

        <nav className="nav">
          {SECTIONS.map((section) => (
            <div className="nav-section" key={section.title}>
              <div className="nav-section-title">{section.title}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? 'active' : ''}`
                  }
                  onClick={() => setOpen(false)}
                >
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
          {devMode && (
            <div className="nav-section nav-section--dev">
              <div className="nav-section-title nav-section-title--dev">
                Developer
              </div>
              <NavLink
                to="/developer"
                className={({ isActive }) =>
                  `nav-link nav-link--dev ${isActive ? 'active' : ''}`
                }
                onClick={() => setOpen(false)}
              >
                <Icon name="developer" />
                <span>Developer Options</span>
              </NavLink>
            </div>
          )}
        </nav>

        <div className="sidebar-footer">
          <ComfyuiBadge compact />
        </div>
      </aside>

      {open && <div className="nav-backdrop" onClick={() => setOpen(false)} />}
    </>
  )
}
