import type { AppSettings, ComfyuiStatus, Health } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (body.detail) detail = String(body.detail)
    } catch {
      // keep default detail
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => request<Health>('/api/health'),
  comfyuiStatus: () => request<ComfyuiStatus>('/api/comfyui/status'),
  getSettings: () => request<AppSettings>('/api/settings'),
  updateSettings: (body: Partial<AppSettings>) =>
    request<AppSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
