export interface ComfyuiStatus {
  connected: boolean
  version: string | null
  detail: string | null
}

export interface AppSettings {
  comfyui_http_url: string
  comfyui_ws_url: string
  jpeg_quality: number
  thumb_max_dim: number
}

export interface Health {
  status: string
  comfyui_connected: boolean
}
