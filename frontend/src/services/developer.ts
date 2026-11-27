import type { DeveloperStatus, ResetReport } from '../types/developer'

export function getDeveloperStatus(): Promise<DeveloperStatus> {
  return fetch('/api/developer/status').then(async (res) => {
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return (await res.json()) as DeveloperStatus
  })
}

// The destructive reset returns a structured report in the body on both success
// and failure, so this reads the JSON body regardless of status and only throws
// for the non-success cases (with diagnostics attached to the error).
export async function resetApplicationData(
  confirm: string,
): Promise<ResetReport> {
  const res = await fetch('/api/developer/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm }),
  })
  let body: (ResetReport & { detail?: unknown }) | null = null
  try {
    body = (await res.json()) as ResetReport & { detail?: unknown }
  } catch {
    // non-JSON body
  }
  if (res.ok && body && body.ok) return body

  const message =
    (body && body.error) ||
    (body && body.detail ? String(body.detail) : `${res.status} ${res.statusText}`)
  const err = new Error(message) as Error & { report?: ResetReport }
  if (body && typeof body.ok === 'boolean') err.report = body
  throw err
}
