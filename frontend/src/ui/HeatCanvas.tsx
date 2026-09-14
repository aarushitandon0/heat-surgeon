import { useEffect, useMemo, useRef, useState } from 'react'
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
import { lerpGrid, paintGrid, type Domain, type Grid } from '../lib/thermal.ts'
import type { GridShape } from '../types/contracts.ts'
import { useElementSize } from './hooks.ts'
import { readMonoFont, readSurfaceColor, readThermalRamp } from './tokens.ts'

const MARGIN_PX = 32
const GRATICULE_LINES = 8
const SCALE_BAR_TARGET = 5
const LABEL_FONT_PX = 12

export type CellToScreen = (col: number, row: number) => [number, number]

export interface OverlayContext {
  ctx: CanvasRenderingContext2D
  cellToScreen: CellToScreen
  view: View
  cell_px: number
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
  /** Non-data marks drawn over the grid (interventions, extents), in surface colours only. */
  overlay?: (overlay: OverlayContext) => void
  ariaLabel: string
}

/** A measured or modelled surface temperature grid, north up, at its true position on a UTM graticule. */
export function HeatCanvas({ values, valuesTo, progress = 0, affine, shape, domain, frame, overlay, ariaLabel }: HeatCanvasProps) {
  const [wrapRef, size] = useElementSize<HTMLDivElement>()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
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

    const rule = readSurfaceColor('--rule')
    const paperDim = readSurfaceColor('--paper-dim')

    // Graticule on real UTM multiples.
    const [westE_m, northN_m] = screenToUtm(view, 0, 0)
    const [eastE_m, southN_m] = screenToUtm(view, size.width_px, size.height_px)
    const step_m = niceStep(Math.max(eastE_m - westE_m, northN_m - southN_m), GRATICULE_LINES)
    ctx.strokeStyle = rule
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

    // The grid: one pixel per cell, placed and rotated by the cell affine, never smoothed.
    const [rows, cols] = shape
    const image = document.createElement('canvas')
    image.width = cols
    image.height = rows
    image.getContext('2d')!.putImageData(new ImageData(paintGrid(drawn, domain, readThermalRamp()), cols, rows), 0, 0)
    ctx.save()
    ctx.transform(...cellCanvasTransform(view, affine))
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(image, 0, 0)
    ctx.restore()

    const cell_px = view.scale_px_per_m * Math.hypot(affine.e_per_col_m, affine.n_per_col_m)
    overlay?.({ ctx, view, cell_px, cellToScreen: (col, row) => utmToScreen(view, ...cellToUtm(affine, col, row)) })

    // Scale bar, bottom left.
    const bar_m = niceStep(size.width_px / view.scale_px_per_m, SCALE_BAR_TARGET)
    const bar_px = bar_m * view.scale_px_per_m
    const baseY = size.height_px - 12.5
    ctx.strokeStyle = paperDim
    ctx.beginPath()
    ctx.moveTo(12, baseY)
    ctx.lineTo(12 + bar_px, baseY)
    ctx.stroke()
    ctx.fillStyle = paperDim
    ctx.font = readMonoFont(LABEL_FONT_PX)
    ctx.textBaseline = 'bottom'
    ctx.fillText(`${formatCount(bar_m)} m`, 12, baseY - 4)
  }, [view, size.width_px, size.height_px, drawn, domain, affine, shape, overlay])

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!view) return
    const rect = event.currentTarget.getBoundingClientRect()
    const [e_m, n_m] = screenToUtm(view, event.clientX - rect.left, event.clientY - rect.top)
    const [col, row] = utmToCell(affine, e_m, n_m).map(Math.floor)
    const [rows, cols] = shape
    setHover(row >= 0 && row < rows && col >= 0 && col < cols ? { row, col } : null)
  }

  const hoverValue = hover ? drawn[hover.row][hover.col] : null

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
      </div>
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
