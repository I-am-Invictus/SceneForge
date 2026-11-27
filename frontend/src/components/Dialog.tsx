import type { ReactNode } from 'react'

interface DialogProps {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}

export function Dialog({ title, onClose, children, wide }: DialogProps) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className={`dialog ${wide ? 'dialog--wide' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-header">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
