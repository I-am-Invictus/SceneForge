interface WorkspacePlaceholderProps {
  title: string
  description: string
  phase: string
}

export function WorkspacePlaceholder({
  title,
  description,
  phase,
}: WorkspacePlaceholderProps) {
  return (
    <div className="page">
      <header className="page-header">
        <h1>{title}</h1>
      </header>
      <div className="placeholder-card">
        <div className="placeholder-glyph">◈</div>
        <h2>{title} workspace</h2>
        <p>{description}</p>
        <span className="placeholder-phase">{phase}</span>
      </div>
    </div>
  )
}
