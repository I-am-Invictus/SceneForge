export interface DeveloperStatus {
  dev_mode: boolean
}

export interface ResetReport {
  ok: boolean
  before: Record<string, number>
  after: Record<string, number>
  files_removed: number
  orphans_removed: number
  backup_path: string | null
  error: string | null
}
