import { useCallback, useState } from 'react'

export interface GalleryTarget {
  clientId: string
  outputId: number
}

/**
 * Shared "Add to Gallery" state for job results, so General Generation, Image
 * Modification, and Character Swapping all open the dialog identically. The
 * dialog owns the gallery list and the sync call; this hook only tracks which
 * output the dialog is operating on.
 */
export function useAddToGallery() {
  const [target, setTarget] = useState<GalleryTarget | null>(null)

  const requestAdd = useCallback(
    (clientId: string, outputId: number) => setTarget({ clientId, outputId }),
    [],
  )

  const closeAdd = useCallback(() => setTarget(null), [])

  return { target, requestAdd, closeAdd }
}
