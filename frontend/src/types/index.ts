export interface ComfyuiStatus {
  connected: boolean
  version: string | null
  detail: string | null
}

export interface AppSettings {
  comfyui_http_url: string
  comfyui_ws_url: string
}

export interface Health {
  status: string
  comfyui_connected: boolean
}
