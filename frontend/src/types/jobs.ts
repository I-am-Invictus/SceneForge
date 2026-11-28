export interface WorkflowInput {
  type: string
  required: boolean
  default: unknown
  auto: string | null
}

export interface Workflow {
  id: string
  name: string
  description: string
  category: string
  version: number
  active_version?: number
  enabled: boolean
  inputs: Record<string, WorkflowInput>
  outputs: Record<string, { node_id: string; output_type: string }[]>
}

export type JobStatus =
  | 'pending'
  | 'dispatching'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'interrupted'

export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'interrupted']

// Jobs that have not yet reached ComfyUI (SceneForge's own queue). These can be
// removed; once submitted they can only be cancelled.
export const NOT_STARTED_STATUSES: JobStatus[] = ['pending', 'dispatching']

// Human-readable label for a status (pending/dispatching both read as "queued").
export function statusLabel(status: JobStatus): string {
  if (status === 'pending' || status === 'dispatching') return 'queued'
  return status
}

export interface JobOutput {
  id: number
  node_id: string
  comfyui_filename: string
  width: number | null
  height: number | null
  size_bytes: number | null
  thumbnail_url: string
  original_url: string
}

export interface Job {
  client_id: string
  comfyui_prompt_id: string | null
  workflow_id: string
  workflow_name: string
  workflow_version: number
  category: string
  status: JobStatus
  progress: number
  prompt: string | null
  error: string | null
  inputs: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
  outputs: JobOutput[]
}
