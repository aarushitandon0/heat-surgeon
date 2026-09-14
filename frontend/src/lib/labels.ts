// Placing map labels: road names along centrelines, place names at points, cross streets at the design grid's
// edges. Pure geometry in drawing units (canvas pixels or SVG user units); nothing is drawn here. Labels are
// chrome, not data: they never carry a measured or modelled value.

import type { BasemapWay } from '../types/contracts.ts'
import type { CellPoint } from './basemap.ts'

export type XY = [number, number]
export interface Box {
  x: number
  y: number
  w: number
  h: number
}
export type Align = 'center' | 'left' | 'right'
export interface Label {
  text: string
  x: number
  y: number
  angle_rad: number
  align: Align
  box: Box
}
export type Measure = (text: string) => number

/** OSM highway classes that get road labels, most important first. Everything else stays unlabelled. */
const ROAD_RANK: Record<string, number> = { motorway: 0, trunk: 0, primary: 1, secondary: 2, tertiary: 3 }

export function roadRank(kind: string): number | null {
  return ROAD_RANK[kind] ?? null
}

export function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
}

export function boxInside(inner: Box, outer: Box): boolean {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h
}

/** Axis-aligned box around a w by h rectangle centred at (x, y), rotated by angle_rad, grown by pad on every side. */
export function rotatedBox(x: number, y: number, w: number, h: number, angle_rad: number, pad: number): Box {
  const c = Math.abs(Math.cos(angle_rad))
  const s = Math.abs(Math.sin(angle_rad))
  const bw = w * c + h * s + 2 * pad
  const bh = w * s + h * c + 2 * pad
  return { x: x - bw / 2, y: y - bh / 2, w: bw, h: bh }
}

/** The same direction turned so text along it never reads upside down: an angle in (-90°, 90°]. */
export function uprightAngle(angle_rad: number): number {
  let a = angle_rad
  while (a > Math.PI / 2) a -= Math.PI
  while (a <= -Math.PI / 2) a += Math.PI
  return a
}

function pointAt(path: XY[], cumulative: number[], s: number): XY {
  let i = 1
  while (i < cumulative.length - 1 && cumulative[i] < s) i++
  const span = cumulative[i] - cumulative[i - 1]
  const t = span === 0 ? 0 : (s - cumulative[i - 1]) / span
  const [x0, y0] = path[i - 1]
  const [x1, y1] = path[i]
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]
}

/**
 * Centre and upright angle for a straight label of `width` centred at one of `fractions` of the path's length,
 * trying them in order. A position is used only where the stretch under the label is near straight: no vertex
 * further than maxBend from the chord, and the chord at least 90% of the width.
 */
export function placeOnPath(path: XY[], width: number, fractions: number[], maxBend: number): { x: number; y: number; angle_rad: number } | null {
  if (path.length < 2) return null
  const cumulative = [0]
  for (let i = 1; i < path.length; i++) {
    cumulative.push(cumulative[i - 1] + Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]))
  }
  const length = cumulative[cumulative.length - 1]
  if (length < width) return null
  for (const f of fractions) {
    const s0 = f * length - width / 2
    const s1 = f * length + width / 2
    if (s0 < 0 || s1 > length) continue
    const [ax, ay] = pointAt(path, cumulative, s0)
    const [bx, by] = pointAt(path, cumulative, s1)
    const chord = Math.hypot(bx - ax, by - ay)
    if (chord < 0.9 * width) continue
    let straight = true
    for (let i = 1; i < path.length - 1 && straight; i++) {
      if (cumulative[i] <= s0 || cumulative[i] >= s1) continue
      const [px, py] = path[i]
      straight = Math.abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / chord <= maxBend
    }
    if (straight) return { x: (ax + bx) / 2, y: (ay + by) / 2, angle_rad: uprightAngle(Math.atan2(by - ay, bx - ax)) }
  }
  return null
}

export interface RoadCandidate {
  text: string
  rank: number
  length: number
  paths: XY[][]
}

function pathLength(path: XY[]): number {
  let total = 0
  for (let i = 1; i < path.length; i++) total += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
  return total
}

/**
 * Named roads of rank at most maxRank, grouped by label text and ordered for labelling: the design street first
 * (shown by its display name), then by class, then by drawn length.
 */
export function roadCandidates(
  roads: BasemapWay[],
  project: (e_m: number, n_m: number) => XY,
  maxRank: number,
  street: { osmName: string; label: string },
): RoadCandidate[] {
  const groups = new Map<string, RoadCandidate>()
  for (const way of roads) {
    if (!way.name) continue
    const isStreet = way.name === street.osmName
    const rank = isStreet ? -1 : roadRank(way.kind)
    if (rank === null || rank > maxRank) continue
    const text = isStreet ? street.label : way.name
    const path = way.path.map(([e, n]) => project(e, n))
    const group = groups.get(text) ?? { text, rank, length: 0, paths: [] }
    group.rank = Math.min(group.rank, rank)
    group.length += pathLength(path)
    group.paths.push(path)
    groups.set(text, group)
  }
  return [...groups.values()].sort((a, b) => a.rank - b.rank || b.length - a.length)
}

export interface PlacementOptions {
  max: number
  fractions: number[]
  maxBend: number
  pad: number
}

/** Road labels along their longest drawn stretches, skipping any that leave the bounds or collide. */
export function placeRoadLabels(candidates: RoadCandidate[], measure: Measure, height: number, bounds: Box, occupied: Box[], options: PlacementOptions): Label[] {
  const placed: Label[] = []
  const taken = [...occupied]
  for (const candidate of candidates) {
    if (placed.length >= options.max) break
    const width = measure(candidate.text)
    const paths = [...candidate.paths].sort((a, b) => pathLength(b) - pathLength(a))
    for (const path of paths) {
      const at = placeOnPath(path, width, options.fractions, options.maxBend)
      if (!at) continue
      const box = rotatedBox(at.x, at.y, width, height, at.angle_rad, options.pad)
      if (!boxInside(box, bounds) || taken.some((other) => boxesOverlap(box, other))) continue
      placed.push({ text: candidate.text, ...at, align: 'center', box })
      taken.push(box)
      break
    }
  }
  return placed
}

export interface PointCandidate {
  text: string
  /** Positions to try, in order. */
  anchors: { x: number; y: number; align: Align }[]
}

/** Horizontal labels at the first anchor of each candidate that fits the bounds without colliding. */
export function placePointLabels(candidates: PointCandidate[], measure: Measure, height: number, bounds: Box, occupied: Box[], max: number, pad: number): Label[] {
  const placed: Label[] = []
  const taken = [...occupied]
  for (const candidate of candidates) {
    if (placed.length >= max) break
    const width = measure(candidate.text)
    for (const anchor of candidate.anchors) {
      const left = anchor.align === 'center' ? anchor.x - width / 2 : anchor.align === 'right' ? anchor.x - width : anchor.x
      const box = { x: left - pad, y: anchor.y - height / 2 - pad, w: width + 2 * pad, h: height + 2 * pad }
      if (!boxInside(box, bounds) || taken.some((other) => boxesOverlap(box, other))) continue
      placed.push({ text: candidate.text, x: anchor.x, y: anchor.y, angle_rad: 0, align: anchor.align, box })
      taken.push(box)
      break
    }
  }
  return placed
}

/** Where along a road label placement tries first: the middle, then out towards the ends. */
export const ROAD_LABEL_FRACTIONS = [0.5, 0.35, 0.65, 0.2, 0.8]

export interface DesignGridLabelOptions {
  /** Distance from the grid edge to the label's near side. */
  gap: number
  pad: number
  maxCrossStreets: number
  /** Inside the grid (the preview, which clips at its edge) or outside it (the 2D grid, which has margins). */
  inward: boolean
}

/**
 * The design street's name at the start of its centreline, and the nearest cross streets where they meet the
 * grid's long edges. Drawing coordinates must run with columns downward and rows to the right, as both the
 * stage 02 preview and the stage 03 grid are drawn.
 */
export function designGridLabels(
  roads: { name: string | null; points: CellPoint[] }[],
  shape: [number, number],
  toDraw: (col: number, row: number) => XY,
  street: { osmName: string; label: string },
  measure: Measure,
  height: number,
  bounds: Box,
  options: DesignGridLabelOptions,
): Label[] {
  const [, cols] = shape
  const offset = options.gap + height / 2
  const [cx, cy] = toDraw(cols / 2, 0)
  const [nx, ny] = toDraw(0, 0)
  const [fx, fy] = toDraw(cols, 0)
  // Left-aligned anchors start pad in from the grid's start, so the label's padded box still fits when the grid
  // begins at the edge of the drawing.
  const streetAnchors: PointCandidate['anchors'] = options.inward
    ? [{ x: cx + options.gap + options.pad, y: cy - offset, align: 'left' }]
    : [
        { x: cx - options.gap, y: cy, align: 'right' },
        { x: nx + options.pad, y: ny - offset, align: 'left' },
        { x: fx + options.pad, y: fy + offset, align: 'left' },
      ]
  const crossings = crossStreetCrossings(roads, shape, street.osmName).map((crossing): PointCandidate => {
    const [x0, y0] = toDraw(0, crossing.row)
    const [x1, y1] = toDraw(cols, crossing.row)
    const nearEdge = { x: x0, y: options.inward ? y0 + offset : y0 - offset, align: 'center' as const }
    const farEdge = { x: x1, y: options.inward ? y1 - offset : y1 + offset, align: 'center' as const }
    return { text: crossing.name, anchors: crossing.edge === 'near' ? [nearEdge, farEdge] : [farEdge, nearEdge] }
  })
  return placePointLabels(
    [{ text: street.label, anchors: streetAnchors }, ...crossings],
    measure,
    height,
    bounds,
    [],
    1 + options.maxCrossStreets,
    options.pad,
  )
}

export interface CityLabelCandidate {
  text: string
  /** UTM points on the feature inside the extent, best first. */
  anchors: XY[]
}

/** Rivers, then trunk roads, by length inside the extent: the few names that make a city recognisable. */
export function cityLabelCandidates(ways: BasemapWay[], bounds_m: [number, number, number, number]): CityLabelCandidate[] {
  const [minE, minN, maxE, maxN] = bounds_m
  const inside = ([e, n]: XY) => e > minE && e < maxE && n > minN && n < maxN
  const groups = new Map<string, { river: boolean; length: number; longest: XY[] }>()
  for (const way of ways) {
    const river = way.kind === 'river'
    if (!way.name || !(river || way.kind === 'trunk' || way.kind === 'motorway')) continue
    const points = way.path.filter(inside) as XY[]
    if (points.length < 2) continue
    const length = pathLength(points)
    const group = groups.get(way.name) ?? { river, length: 0, longest: [] }
    group.length += length
    if (length > pathLength(group.longest)) group.longest = points
    groups.set(way.name, group)
  }
  return [...groups.entries()]
    .sort(([, a], [, b]) => Number(b.river) - Number(a.river) || b.length - a.length)
    .map(([text, g]) => ({
      text,
      anchors: [0.5, 0.3, 0.7, 0.15, 0.85].map((f) => g.longest[Math.min(g.longest.length - 1, Math.floor(f * g.longest.length))]),
    }))
}

export interface Crossing {
  name: string
  row: number
  /** 'near' is the grid edge at column 0, 'far' the edge at the last column. */
  edge: 'near' | 'far'
}

/**
 * Where named roads cross the lines just outside the design grid's two long edges (one column beyond each), one
 * crossing per name, nearest the middle of the segment first. One column out catches roads that end at the
 * street (T-junctions) as well as those that cross it. The design street itself is excluded.
 */
export function crossStreetCrossings(roads: { name: string | null; points: CellPoint[] }[], shape: [number, number], excludeName: string): Crossing[] {
  const [rows, cols] = shape
  const best = new Map<string, Crossing>()
  for (const road of roads) {
    if (!road.name || road.name === excludeName) continue
    for (let i = 1; i < road.points.length; i++) {
      const [c0, r0] = road.points[i - 1]
      const [c1, r1] = road.points[i]
      for (const [edgeCol, edge] of [[-1, 'near'], [cols + 1, 'far']] as const) {
        if (c0 === c1 || (c0 - edgeCol) * (c1 - edgeCol) > 0) continue
        const row = r0 + ((edgeCol - c0) / (c1 - c0)) * (r1 - r0)
        if (row < 0 || row > rows) continue
        const current = best.get(road.name)
        if (!current || Math.abs(row - rows / 2) < Math.abs(current.row - rows / 2)) best.set(road.name, { name: road.name, row, edge })
      }
    }
  }
  return [...best.values()].sort((a, b) => Math.abs(a.row - rows / 2) - Math.abs(b.row - rows / 2))
}
