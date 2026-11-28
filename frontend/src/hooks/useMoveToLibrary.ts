import { useCallback, useState } from 'react'
import { addJobOutputToAsset, moveJobOutput } from '../services/jobs'
import type { Job } from '../types/jobs'
import type { AssetKind } from '../types/assets'

export interface MoveTarget {
  clientId: string
  outputId: number
}

/**
 * Shared "Add to Library" behavior for job results, so General Generation,
 * Image Modification, and Character Swapping all move outputs identically.
 *
 * The page owns its job list and supplies `upsertJob` to replace (or prepend)
 * the moved job with the fresh copy returned by the API; this hook owns the
 * pending move target, the API call, and clearing the dialog.
 */
export function useMoveToLibrary(upsertJob: (job: Job) => void) {
  const [moveTarget, setMoveTarget] = useState<MoveTarget | null>(null)

  const requestMove = useCallback(
    (clientId: string, outputId: number) =>
      setMoveTarget({ clientId, outputId }),
    [],
  )

  const handleMove = useCallback(
    async (folder: AssetKind) => {
      if (!moveTarget) return
      const { clientId, outputId } = moveTarget
      const fresh = await moveJobOutput(clientId, outputId, folder)
      upsertJob(fresh)
    },
    [moveTarget, upsertJob],
  )

  const handleAddToExisting = useCallback(
    async (kind: AssetKind, assetId: number, makeDefault: boolean) => {
      if (!moveTarget) return
      const { clientId, outputId } = moveTarget
      const fresh = await addJobOutputToAsset(
        clientId,
        outputId,
        kind,
        assetId,
        makeDefault,
      )
      upsertJob(fresh)
    },
    [moveTarget, upsertJob],
  )

  const closeMove = useCallback(() => setMoveTarget(null), [])

  return { moveTarget, requestMove, handleMove, handleAddToExisting, closeMove }
}
