import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { ComfyuiStatus } from '../types'

const INITIAL: ComfyuiStatus = {
  connected: false,
  version: null,
  detail: 'checking…',
}

export function useComfyuiStatus(intervalMs = 10000): ComfyuiStatus {
  const [status, setStatus] = useState<ComfyuiStatus>(INITIAL)

  useEffect(() => {
    let cancelled = false
    const refresh = () => {
      api
        .comfyuiStatus()
        .then((s) => {
          if (!cancelled) setStatus(s)
        })
        .catch(() => {
          // backend unreachable: keep last known state
        })
    }
    refresh()
    const id = setInterval(refresh, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs])

  return status
}
