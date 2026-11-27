import type { Workflow } from '../types/jobs'
import type {
  WorkflowInspection,
  WorkflowMappings,
  WorkflowTestResult,
  WorkflowUploadPayload,
  WorkflowValidationResult,
  WorkflowVersion,
} from '../types/workflows'

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

function json(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function listWorkflows(): Promise<Workflow[]> {
  return request<Workflow[]>('/api/workflows')
}

export function getWorkflow(id: string): Promise<Workflow> {
  return request<Workflow>(`/api/workflows/${id}`)
}

export function uploadWorkflow(payload: WorkflowUploadPayload): Promise<Workflow> {
  return request<Workflow>('/api/workflows', json(payload))
}

export function patchWorkflow(
  id: string,
  patch: { enabled?: boolean; name?: string; description?: string },
): Promise<Workflow> {
  return request<Workflow>(`/api/workflows/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function listVersions(id: string): Promise<WorkflowVersion[]> {
  return request<WorkflowVersion[]>(`/api/workflows/${id}/versions`)
}

export function uploadVersion(
  id: string,
  payload: {
    workflow: Record<string, unknown>
    inputs: WorkflowMappings['inputs']
    outputs: WorkflowMappings['outputs']
  },
): Promise<WorkflowVersion> {
  return request<WorkflowVersion>(`/api/workflows/${id}/versions`, json(payload))
}

export function inspectVersion(id: string, version: number): Promise<WorkflowInspection> {
  return request<WorkflowInspection>(`/api/workflows/${id}/versions/${version}`)
}

export function getTemplate(id: string, version: number): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/workflows/${id}/versions/${version}/template`)
}

export function saveMappings(
  id: string,
  version: number,
  mappings: WorkflowMappings,
): Promise<WorkflowMappings> {
  return request<WorkflowMappings>(
    `/api/workflows/${id}/versions/${version}/mappings`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mappings),
    },
  )
}

export function validateVersion(id: string, version: number): Promise<WorkflowValidationResult> {
  return request<WorkflowValidationResult>(
    `/api/workflows/${id}/versions/${version}/validate`,
    json({}),
  )
}

export function activateVersion(id: string, version: number): Promise<{ active_version: number }> {
  return request<{ active_version: number }>(
    `/api/workflows/${id}/versions/${version}/activate`,
    json({}),
  )
}

export function testWorkflow(
  id: string,
  body: { version?: number; test_inputs: Record<string, unknown> },
): Promise<WorkflowTestResult> {
  return request<WorkflowTestResult>(`/api/workflows/${id}/test`, json(body))
}
