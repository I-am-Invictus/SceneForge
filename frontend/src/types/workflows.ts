import type { WorkflowInput } from './jobs'

export interface OutputRef {
  node_id: string
  output_type: string
}

export interface WorkflowVersion {
  id: string
  version: number
  is_active: boolean
  inputs: Record<string, WorkflowInput>
  outputs: Record<string, OutputRef[]>
}

// --- Inspection report (object_info-backed) --------------------------------

export interface NodeInputReport {
  name: string
  value: unknown
  is_link: boolean
  is_combo: boolean
  types: string[] | null
  optional: boolean
  hint: string | null
}

export interface NodeReport {
  id: string
  class_type: string
  present: boolean
  is_image_loader: boolean
  inputs: NodeInputReport[]
}

export interface RefField {
  node_id: string
  field: string
}

export interface ReferencedModel {
  node_id: string
  field: string
  value: string
  found: boolean
}

export interface WorkflowReport {
  node_count: number
  nodes: NodeReport[]
  image_loaders: string[]
  text_inputs: RefField[]
  seed_inputs: RefField[]
  dimension_inputs: RefField[]
  numeric_inputs: RefField[]
  boolean_inputs: RefField[]
  combo_inputs: RefField[]
  output_nodes: string[]
  custom_classes: string[]
  missing_classes: string[]
  referenced_models: ReferencedModel[]
}

export interface StoredInput extends InputMappingRaw {
  name?: string
}

export interface WorkflowInspection {
  id: string
  version: number
  is_active: boolean
  active_version: number
  object_info_available: boolean
  report: WorkflowReport
  inputs: Record<string, StoredInput>
  outputs: Record<string, OutputRef[]>
}

// --- Validation / test ------------------------------------------------------

export interface Connectivity {
  connected: boolean
  version?: string | null
  detail?: string | null
}

export interface WorkflowValidationResult {
  id: string
  version: number
  ok: boolean
  connectivity: Connectivity | null
  errors: string[]
  warnings: string[]
}

export interface WorkflowTestResult {
  id: string
  ok: boolean
  connectivity: Connectivity | null
  issues: string[]
  version: number | null
  warnings: string[]
  submitted: boolean
  job_client_id: string | null
}

// --- Mappings / upload payloads --------------------------------------------

export type InputType =
  | 'text'
  | 'image'
  | 'number'
  | 'boolean'
  | 'combo'
  | 'seed'
  | 'width'
  | 'height'

export const INPUT_TYPES: InputType[] = [
  'text',
  'image',
  'number',
  'boolean',
  'combo',
  'seed',
  'width',
  'height',
]

export interface InputMappingRaw {
  node_id: string
  input_name: string
  type: InputType
  required: boolean
  default?: unknown
  auto?: string | null
}

export interface WorkflowMappings {
  inputs: Record<string, InputMappingRaw>
  outputs: Record<string, OutputRef[]>
}

export interface WorkflowUploadPayload {
  id: string
  name: string
  category: string
  description: string
  workflow: Record<string, unknown>
  inputs: Record<string, InputMappingRaw>
  outputs: Record<string, OutputRef[]>
}

export const CATEGORIES = [
  'general_generation',
  'image_modification',
  'character_swap',
] as const

export const CATEGORY_LABEL: Record<string, string> = {
  general_generation: 'General generation',
  image_modification: 'Image modification',
  character_swap: 'Character swap',
}
