export type AssetKind = 'character' | 'scene'

export interface Folder {
  id: number
  kind: string
  name: string
  parent_id: number | null
}

export interface AssetFile {
  id: number
  display_name: string
  width: number
  height: number
  size_bytes: number
  mime: string
  is_default: boolean
  sort_order: number
  created_at: string
  thumbnail_url: string
  original_url: string
}

export interface Asset {
  id: number
  kind: string
  name: string
  description: string | null
  tags: string[]
  folder_id: number | null
  is_favorite: boolean
  created_at: string
  updated_at: string
  files: AssetFile[]
  thumbnail_url: string | null
  reference_count: number
}
