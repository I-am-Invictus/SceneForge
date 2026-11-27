import type { Job, Workflow } from '../types/jobs'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
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

export function listWorkflows(): Promise<Workflow[]> {
  return request<Workflow[]>('/api/workflows')
}

export function generate(
  workflowId: string,
  inputs: Record<string, unknown>,
): Promise<Job> {
  return request<Job>(`/api/generate/${workflowId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inputs }),
  })
}

export function listJobs(
  params: { workflow_id?: string; status?: string; limit?: number } = {},
): Promise<Job[]> {
  const search = new URLSearchParams()
  if (params.workflow_id) search.set('workflow_id', params.workflow_id)
  if (params.status) search.set('status', params.status)
  if (params.limit != null) search.set('limit', String(params.limit))
  const qs = search.toString()
  return request<Job[]>(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export function getJob(clientId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${clientId}`)
}

export function cancelJob(clientId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${clientId}/cancel`, { method: 'POST' })
}

export function deleteJobOutput(
  clientId: string,
  outputId: number,
): Promise<Job> {
  return request<Job>(`/api/jobs/${clientId}/outputs/${outputId}`, {
    method: 'DELETE',
  })
}
