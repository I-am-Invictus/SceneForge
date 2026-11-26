import type { ReactNode } from 'react'

interface DialogProps {
  title: string
  onClose: () => void
  children: ReactNode
}

export function Dialog({ title, onClose, children }: DialogProps) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
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
