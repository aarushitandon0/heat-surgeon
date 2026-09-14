// Stroking OpenStreetMap context onto a canvas in surface colours. Context, not data: never the thermal ramp.

import { roadWeight, type CellPoint, type DesignGridContext } from '../lib/basemap.ts'
import type { BasemapWay, PointUTM } from '../types/contracts.ts'
import { readSurfaceColor } from './tokens.ts'

type Project = (x: number, y: number) => [number, number]

export interface ContextStyle {
  buildingAlpha: number
  minorAlpha: number
  majorAlpha: number
  buildingWidth_px: number
  minorWidth_px: number
  majorWidth_px: number
}

function strokePaths(ctx: CanvasRenderingContext2D, paths: readonly (readonly [number, number])[][], project: Project, width_px: number, alpha: number) {
  if (paths.length === 0) return
  ctx.globalAlpha = alpha
  ctx.lineWidth = width_px
  ctx.beginPath()
  for (const path of paths) {
    path.forEach(([a, b], i) => {
      const [x, y] = project(a, b)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
  }
  ctx.stroke()
}

/** Building rings, then minor roads, then major roads, each as one stroke. */
export function strokeBasemap(ctx: CanvasRenderingContext2D, roads: BasemapWay[], buildings: PointUTM[][], project: Project, style: ContextStyle) {
  ctx.save()
  ctx.strokeStyle = readSurfaceColor('--paper')
  ctx.lineJoin = 'round'
  strokePaths(ctx, buildings, project, style.buildingWidth_px, style.buildingAlpha)
  strokePaths(ctx, roads.filter((w) => roadWeight(w.kind) === 'minor').map((w) => w.path), project, style.minorWidth_px, style.minorAlpha)
  strokePaths(ctx, roads.filter((w) => roadWeight(w.kind) === 'major').map((w) => w.path), project, style.majorWidth_px, style.majorAlpha)
  ctx.restore()
}

/** The same, for context already placed in design-grid cell space. */
export function strokeGridContext(ctx: CanvasRenderingContext2D, context: DesignGridContext, cellToScreen: Project, style: ContextStyle) {
  ctx.save()
  ctx.strokeStyle = readSurfaceColor('--paper')
  ctx.lineJoin = 'round'
  const byWeight = (weight: 'minor' | 'major'): CellPoint[][] => context.roads.filter((r) => r.weight === weight).map((r) => r.points)
  strokePaths(ctx, context.buildings, cellToScreen, style.buildingWidth_px, style.buildingAlpha)
  strokePaths(ctx, byWeight('minor'), cellToScreen, style.minorWidth_px, style.minorAlpha)
  strokePaths(ctx, byWeight('major'), cellToScreen, style.majorWidth_px, style.majorAlpha)
  ctx.restore()
}
