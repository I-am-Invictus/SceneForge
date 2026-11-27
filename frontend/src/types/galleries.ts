export interface GalleryCover {
  thumbnail_url: string
  original_url: string
  width: number | null
  height: number | null
  label: string
}

export interface Gallery {
  id: number
  name: string
  image_count: number
  cover: GalleryCover | null
  created_at: string
  updated_at: string
}

export interface GalleryBrief {
  id: number
  name: string
}

export interface GalleryOriginal {
  url: string
  width: number | null
  height: number | null
  alt: string
}

export interface GalleryImage {
  output_id: number
  job_client_id: string
  job_category: string
  comfyui_filename: string
  prompt: string | null
  width: number | null
  height: number | null
  thumbnail_url: string
  original_url: string
  /** Resolved source image for before/after comparison; null for general
   *  generation or when the source no longer exists. */
  original: GalleryOriginal | null
}
