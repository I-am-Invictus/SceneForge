import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'

export interface CompareImage {
  src: string
  alt?: string
  width?: number
  height?: number
}

export type CompareMode = 'slider' | 'side-by-side' | 'original' | 'generated'

const MODES: { id: CompareMode; label: string }[] = [
  { id: 'slider', label: 'Before / After' },
  { id: 'side-by-side', label: 'Side by side' },
  { id: 'original', label: 'Original' },
  { id: 'generated', label: 'Generated' },
]

interface ImageComparisonProps {
  /** Original (source) image. When null the component degrades gracefully to
   *  generated-only with no comparison controls. */
  original: CompareImage | null
  generated: CompareImage
  /** Identity of the displayed result (e.g. `${jobId}:${outputIndex}`). When
   *  it changes the slider resets to midpoint; the selected mode persists. */
  resultKey: string
  onPrev?: () => void
  onNext?: () => void
  canPrev?: boolean
  canNext?: boolean
}

export function ImageComparison({
  original,
  generated,
  resultKey,
  onPrev,
  onNext,
  canPrev,
  canNext,
}: ImageComparisonProps) {
  const [mode, setMode] = useState<CompareMode>(
    original ? 'slider' : 'generated',
  )
  const [pos, setPos] = useState(50)
  const [originalFailed, setOriginalFailed] = useState(false)
  const frameRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  useEffect(() => {
    setPos(50)
  }, [resultKey])

  useEffect(() => {
    setOriginalFailed(false)
  }, [original?.src])

  // A source image that no longer exists (deleted asset) degrades the view
  // to generated-only instead of showing a broken image.
  const effectiveOriginal = original && !originalFailed ? original : null

  const effectiveMode: CompareMode = effectiveOriginal ? mode : 'generated'

  const aspect =
    generated.width && generated.height
      ? `${generated.width} / ${generated.height}`
      : '4 / 3'

  function updateFromClientX(clientX: number) {
    const el = frameRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.width <= 0) return
    const pct = ((clientX - rect.left) / rect.width) * 100
    setPos(Math.min(100, Math.max(0, pct)))
  }

  const sliderHandlers =
    effectiveMode === 'slider' && effectiveOriginal
      ? {
          onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => {
            dragging.current = true
            e.currentTarget.setPointerCapture(e.pointerId)
            updateFromClientX(e.clientX)
          },
          onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => {
            if (dragging.current) updateFromClientX(e.clientX)
          },
          onPointerUp: () => {
            dragging.current = false
          },
          onPointerCancel: () => {
            dragging.current = false
          },
        }
      : {}

  let stage: ReactNode
  if (effectiveMode === 'slider' && effectiveOriginal) {
    stage = (
      <div
        ref={frameRef}
        className="compare-frame compare-frame--slider"
        style={{ aspectRatio: aspect }}
        {...sliderHandlers}
      >
        <img
          className="compare-img"
          src={generated.src}
          alt={generated.alt ?? 'Generated'}
          draggable={false}
        />
        <img
          className="compare-img compare-img--clip"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
          src={effectiveOriginal.src}
          alt={effectiveOriginal.alt ?? 'Original'}
          draggable={false}
          onError={() => setOriginalFailed(true)}
        />
        <div className="compare-divider" style={{ left: `${pos}%` }}>
          <button
            type="button"
            className="compare-grip"
            aria-label="Drag to compare"
            role="slider"
            aria-valuenow={Math.round(pos)}
            aria-valuemin={0}
            aria-valuemax={100}
            onKeyDown={(e) => {
              if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - 2))
              if (e.key === 'ArrowRight') setPos((p) => Math.min(100, p + 2))
            }}
          >
            ⇔
          </button>
        </div>
        <span className="compare-tag compare-tag--left">Original</span>
        <span className="compare-tag compare-tag--right">Generated</span>
      </div>
    )
  } else if (effectiveMode === 'side-by-side' && effectiveOriginal) {
    stage = (
      <div className="compare-sbs">
        <div className="compare-sbs-pane" style={{ aspectRatio: aspect }}>
          <img
            src={effectiveOriginal.src}
            alt={effectiveOriginal.alt ?? 'Original'}
            draggable={false}
            onError={() => setOriginalFailed(true)}
          />
          <span className="compare-tag compare-tag--left">Original</span>
        </div>
        <div className="compare-sbs-pane" style={{ aspectRatio: aspect }}>
          <img
            src={generated.src}
            alt={generated.alt ?? 'Generated'}
            draggable={false}
          />
          <span className="compare-tag compare-tag--right">Generated</span>
        </div>
      </div>
    )
  } else if (effectiveMode === 'original' && effectiveOriginal) {
    stage = (
      <div className="compare-frame" style={{ aspectRatio: aspect }}>
        <img
          className="compare-img"
          src={effectiveOriginal.src}
          alt={effectiveOriginal.alt ?? 'Original'}
          draggable={false}
          onError={() => setOriginalFailed(true)}
        />
        <span className="compare-tag compare-tag--left">Original</span>
      </div>
    )
  } else {
    stage = (
      <div className="compare-frame" style={{ aspectRatio: aspect }}>
        <img
          className="compare-img"
          src={generated.src}
          alt={generated.alt ?? 'Generated'}
          draggable={false}
        />
      </div>
    )
  }

  return (
    <div className="image-comparison">
      <div className="image-comparison-stage">
        {stage}
        {onPrev && (
          <button
            type="button"
            className="compare-nav compare-nav--prev"
            onClick={onPrev}
            disabled={!canPrev}
            aria-label="Previous result"
          >
            ‹
          </button>
        )}
        {onNext && (
          <button
            type="button"
            className="compare-nav compare-nav--next"
            onClick={onNext}
            disabled={!canNext}
            aria-label="Next result"
          >
            ›
          </button>
        )}
      </div>
      {effectiveOriginal && (
        <div className="compare-modes" role="group" aria-label="Comparison mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={m.id === mode ? 'active' : ''}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
