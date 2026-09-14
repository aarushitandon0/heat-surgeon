import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  cellCanvasTransform,
  cellToUtm,
  fitView,
  gridBounds,
  niceStep,
  screenToUtm,
  stepsWithin,
  utmToCell,
  utmToScreen,
  type BoundsUTM,
  type CellAffine,
  type View,
} from '../lib/geometry.ts'
import { TEMP_DECIMALS, formatCount, formatNumber } from '../lib/format.ts'
import type { Box } from '../lib/labels.ts'
import { lerpGrid, paintGrid, type Domain, type Grid } from '../lib/thermal.ts'
import type { GridShape } from '../types/contracts.ts'
import { useElementSize } from './hooks.ts'
import { readSurfaceColor, readThermalRamp } from './tokens.ts'

const MARGIN_PX = 32
const GRATICULE_LINES = 8
/** The scale bar is the 1, 2 or 5 × 10^k metres nearest this many pixels. */
const SCALE_BAR_TARGET_PX = 120

export type CellToScreen = (col: number, row: number) => [number, number]

export interface OverlayContext {
  ctx: CanvasRenderingContext2D
  cellToScreen: CellToScreen
  view: View
  cell_px: number
  width_px: number
  height_px: number
  /** Screen boxes covered by HTML on top of the canvas (the inset), for labels to avoid. */
  reserved: Box[]
}

interface HeatCanvasProps {
  /** Surface temperature grid, row-major, null where there is no value. */
  values: Grid
  /** When given, the drawn grid is values interpolated towards this by `progress`. */
  valuesTo?: Grid
  progress?: number
  affine: CellAffine
  shape: GridShape
  domain: Domain
  /** Extent to frame; defaults to the grid's own bounds. */
  frame?: BoundsUTM
  /** Context drawn under the grid (streets, footprints), in surface colours only. */
  underlay?: (overlay: OverlayContext) => void
  /** Opacity of the grid over the underlay. The legend bar must be drawn at the same opacity. */
  gridOpacity?: number
  /** Non-data marks drawn over the grid (interventions, extents), in surface colours only. */
  overlay?: (overlay: OverlayContext) => void
  /** A small figure pinned to the frame's top right, such as a locator. */
  inset?: ReactNode
  ariaLabel: string
}

/** A measured or modelled surface temperature grid, north up, at its true position on a UTM graticule. */
export function HeatCanvas({
  values,
  valuesTo,
  progress = 0,
  affine,
  shape,
  domain,
  frame,
  underlay,
  gridOpacity = 1,
  overlay,
  inset,
  ariaLabel,
}: HeatCanvasProps) {
  const [wrapRef, size] = useElementSize<HTMLDivElement>()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const insetRef = useRef<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null)

  const bounds = useMemo(() => frame ?? gridBounds(affine, shape), [frame, affine, shape])
  const view = useMemo(
    () => (size.width_px > 0 && size.height_px > 0 ? fitView(bounds, size.width_px, size.height_px, MARGIN_PX) : null),
    [bounds, size.width_px, size.height_px],
  )
  const drawn = useMemo(
    () => (valuesTo && progress > 0 ? lerpGrid(values, valuesTo, progress) : values),
    [values, valuesTo, progress],
  )

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || !view) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(size.width_px * dpr)
    canvas.height = Math.round(size.height_px * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size.width_px, size.height_px)

    // Graticule on real UTM multiples.
    const [westE_m, northN_m] = screenToUtm(view, 0, 0)
    const [eastE_m, southN_m] = screenToUtm(view, size.width_px, size.height_px)
    const step_m = niceStep(Math.max(eastE_m - westE_m, northN_m - southN_m), GRATICULE_LINES)
    ctx.strokeStyle = readSurfaceColor('--rule')
    ctx.lineWidth = 1
    ctx.beginPath()
    for (const e_m of stepsWithin(westE_m, eastE_m, step_m)) {
      const x = Math.round(utmToScreen(view, e_m, 0)[0]) + 0.5
      ctx.moveTo(x, 0)
      ctx.lineTo(x, size.height_px)
    }
    for (const n_m of stepsWithin(southN_m, northN_m, step_m)) {
      const y = Math.round(utmToScreen(view, 0, n_m)[1]) + 0.5
      ctx.moveTo(0, y)
      ctx.lineTo(size.width_px, y)
    }
    ctx.stroke()

    const cell_px = view.scale_px_per_m * Math.hypot(affine.e_per_col_m, affine.n_per_col_m)
    const frameRect = canvas.parentElement?.getBoundingClientRect()
    const insetRect = insetRef.current?.getBoundingClientRect()
    const reserved: Box[] =
      frameRect && insetRect
        ? [{ x: insetRect.left - frameRect.left, y: insetRect.top - frameRect.top, w: insetRect.width, h: insetRect.height }]
        : []
    const context: OverlayContext = {
      ctx,
      view,
      cell_px,
      width_px: size.width_px,
      height_px: size.height_px,
      reserved,
      cellToScreen: (col, row) => utmToScreen(view, ...cellToUtm(affine, col, row)),
    }
    underlay?.(context)

    // The grid: one pixel per cell, placed and rotated by the cell affine, never smoothed.
    const [rows, cols] = shape
    const image = document.createElement('canvas')
    image.width = cols
    image.height = rows
    image.getContext('2d')!.putImageData(new ImageData(paintGrid(drawn, domain, readThermalRamp()), cols, rows), 0, 0)
    ctx.save()
    ctx.globalAlpha = gridOpacity
    ctx.transform(...cellCanvasTransform(view, affine))
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(image, 0, 0)
    ctx.restore()

    overlay?.(context)
  }, [view, size.width_px, size.height_px, drawn, domain, affine, shape, underlay, gridOpacity, overlay])

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!view) return
    const rect = event.currentTarget.getBoundingClientRect()
    const [e_m, n_m] = screenToUtm(view, event.clientX - rect.left, event.clientY - rect.top)
    const [col, row] = utmToCell(affine, e_m, n_m).map(Math.floor)
    const [rows, cols] = shape
    setHover(row >= 0 && row < rows && col >= 0 && col < cols ? { row, col } : null)
  }

  const hoverValue = hover ? drawn[hover.row][hover.col] : null
  const bar_m = view ? niceStep(SCALE_BAR_TARGET_PX / view.scale_px_per_m, 1) : null

  return (
    <div className="heat-canvas">
      <div className="heat-canvas-frame" ref={wrapRef}>
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={ariaLabel}
          style={{ width: size.width_px, height: size.height_px }}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
        />
        {inset && (
          <div className="heat-canvas-inset" ref={insetRef}>
            {inset}
          </div>
        )}
      </div>
      {view && bar_m !== null && (
        <p className="scale-bar">
          <span className="scale-bar-line" style={{ width: `${bar_m * view.scale_px_per_m}px` }} aria-hidden="true" />
          <span className="mono">{formatCount(bar_m)} m</span>
        </p>
      )}
      <p className="heat-canvas-hover" aria-live="off">
        {hover ? (
          <>
            Cell row <span className="mono">{hover.row}</span>, column <span className="mono">{hover.col}</span>
            {': '}
            {hoverValue === null ? 'no value' : <span className="mono">{formatNumber(hoverValue, TEMP_DECIMALS)} °C</span>}
          </>
        ) : (
          'Point at a cell to read its value.'
        )}
      </p>
    </div>
  )
}
