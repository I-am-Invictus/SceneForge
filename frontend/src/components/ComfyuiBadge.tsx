import { useComfyuiStatus } from '../hooks/useComfyuiStatus'

export function ComfyuiBadge({ compact = false }: { compact?: boolean }) {
  const status = useComfyuiStatus()
  const label = compact
    ? status.connected
      ? 'ComfyUI online'
      : 'ComfyUI offline'
    : status.connected
      ? `ComfyUI connected${status.version ? ` · v${status.version}` : ''}`
      : 'ComfyUI disconnected'

  return (
    <div className={`comfyui-badge ${status.connected ? 'ok' : 'off'}`} title={status.detail ?? label}>
      <span className="comfyui-dot" />
      {label}
    </div>
  )
}
