import type {
  Gallery,
  GalleryBrief,
  GalleryImage,
} from '../types/galleries'

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

export function listGalleries(): Promise<Gallery[]> {
  return request<Gallery[]>('/api/galleries')
}

export function getGallery(id: number): Promise<Gallery> {
  return request<Gallery>(`/api/galleries/${id}`)
}

export function createGallery(name: string): Promise<Gallery> {
  return request<Gallery>('/api/galleries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function renameGallery(id: number, name: string): Promise<Gallery> {
  return request<Gallery>(`/api/galleries/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteGallery(id: number): Promise<void> {
  return request<void>(`/api/galleries/${id}`, { method: 'DELETE' })
}

export function listGalleryImages(id: number): Promise<GalleryImage[]> {
  return request<GalleryImage[]>(`/api/galleries/${id}/images`)
}

export function removeGalleryImage(
  id: number,
  outputId: number,
): Promise<Gallery> {
  return request<Gallery>(`/api/galleries/${id}/images/${outputId}`, {
    method: 'DELETE',
  })
}

export function getOutputGalleries(outputId: number): Promise<GalleryBrief[]> {
  return request<GalleryBrief[]>(`/api/job-outputs/${outputId}/galleries`)
}

export function syncOutputGalleries(
  outputId: number,
  galleryIds: number[],
): Promise<GalleryBrief[]> {
  return request<GalleryBrief[]>(`/api/job-outputs/${outputId}/galleries`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gallery_ids: galleryIds }),
  })
}
