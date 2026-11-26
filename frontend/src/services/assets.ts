import type { Asset, AssetKind, Folder } from '../types/assets'

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
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function base(kind: AssetKind) {
  return `/api/libraries/${kind}`
}

export function listAssets(
  kind: AssetKind,
  params: { q?: string; folder_id?: number | null; favorite?: boolean } = {},
): Promise<Asset[]> {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.folder_id != null) search.set('folder_id', String(params.folder_id))
  if (params.favorite) search.set('favorite', 'true')
  const qs = search.toString()
  return request<Asset[]>(`${base(kind)}/assets${qs ? `?${qs}` : ''}`)
}

export function getAsset(kind: AssetKind, id: number): Promise<Asset> {
  return request<Asset>(`${base(kind)}/assets/${id}`)
}

export function createAssets(
  kind: AssetKind,
  files: FileList | File[],
  name?: string,
  folderId?: number | null,
): Promise<Asset[]> {
  const form = new FormData()
  if (name) form.append('name', name)
  if (folderId != null) form.append('folder_id', String(folderId))
  for (const file of Array.from(files)) form.append('files', file)
  return request<Asset[]>(base(kind) + '/assets', { method: 'POST', body: form })
}

export function patchAsset(
  kind: AssetKind,
  id: number,
  patch: { name?: string; is_favorite?: boolean },
): Promise<Asset> {
  return request<Asset>(`${base(kind)}/assets/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function moveAsset(
  kind: AssetKind,
  id: number,
  folderId: number | null,
): Promise<Asset> {
  return request<Asset>(`${base(kind)}/assets/${id}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
}

export function deleteAsset(kind: AssetKind, id: number): Promise<void> {
  return request<void>(`${base(kind)}/assets/${id}`, { method: 'DELETE' })
}

export function addReferences(
  kind: AssetKind,
  id: number,
  files: FileList | File[],
): Promise<Asset> {
  const form = new FormData()
  for (const file of Array.from(files)) form.append('files', file)
  return request<Asset>(`${base(kind)}/assets/${id}/files`, {
    method: 'POST',
    body: form,
  })
}

export function deleteFile(kind: AssetKind, assetId: number, fileId: number): Promise<Asset> {
  return request<Asset>(`${base(kind)}/assets/${assetId}/files/${fileId}`, {
    method: 'DELETE',
  })
}

export function setDefaultFile(
  kind: AssetKind,
  assetId: number,
  fileId: number,
): Promise<Asset> {
  return request<Asset>(`${base(kind)}/assets/${assetId}/files/${fileId}/default`, {
    method: 'POST',
  })
}

export function listFolders(kind: AssetKind): Promise<Folder[]> {
  return request<Folder[]>(base(kind) + '/folders')
}

export function createFolder(
  kind: AssetKind,
  name: string,
  parentId?: number | null,
): Promise<Folder> {
  return request<Folder>(base(kind) + '/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId ?? null }),
  })
}

export function renameFolder(kind: AssetKind, id: number, name: string): Promise<Folder> {
  return request<Folder>(`${base(kind)}/folders/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteFolder(kind: AssetKind, id: number): Promise<void> {
  return request<void>(`${base(kind)}/folders/${id}`, { method: 'DELETE' })
}
