// OpenStreetMap context geometry: which ways to draw, and placing it on the street-aligned design grid.
// Display only. Nothing here is a measurement or a model input.

import type { BasemapWay, DesignGrid, PointUTM } from '../types/contracts.ts'
import { affineFromDesignGrid, gridBounds, utmToCell, type BoundsUTM } from './geometry.ts'

export type RoadWeight = 'major' | 'minor' | 'path'

const MAJOR_ROADS = new Set([
  'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link',
])
const PATHS = new Set(['footway', 'path', 'steps', 'cycleway', 'corridor', 'pedestrian', 'track', 'bridleway', 'elevator', 'platform'])
/** City-scale classes drawn heavier in the locator; secondary roads are drawn lighter. */
const CITY_MAJOR_ROADS = new Set(['motorway', 'trunk', 'primary'])

/** How heavily to draw an OSM highway value. Paths are left out of the drawing; they clutter at street scale. */
export function roadWeight(kind: string): RoadWeight {
  if (MAJOR_ROADS.has(kind)) return 'major'
  if (PATHS.has(kind)) return 'path'
  return 'minor'
}

export type CityWayClass = 'river' | 'major' | 'minor'

export function cityWayClass(kind: string): CityWayClass {
  if (kind === 'river') return 'river'
  return CITY_MAJOR_ROADS.has(kind) ? 'major' : 'minor'
}

export function boundsFromArray([min_e_m, min_n_m, max_e_m, max_n_m]: [number, number, number, number]): BoundsUTM {
  return { min_e_m, min_n_m, max_e_m, max_n_m }
}

export function expandBounds(bounds: BoundsUTM, margin_m: number): BoundsUTM {
  return {
    min_e_m: bounds.min_e_m - margin_m,
    max_e_m: bounds.max_e_m + margin_m,
    min_n_m: bounds.min_n_m - margin_m,
    max_n_m: bounds.max_n_m + margin_m,
  }
}

/** True when the path's own bounding box overlaps the bounds. Cheap, and never drops a path that crosses them. */
export function pathTouches(path: PointUTM[], bounds: BoundsUTM): boolean {
  let min_e = Infinity
  let max_e = -Infinity
  let min_n = Infinity
  let max_n = -Infinity
  for (const [e, n] of path) {
    if (e < min_e) min_e = e
    if (e > max_e) max_e = e
    if (n < min_n) min_n = n
    if (n > max_n) max_n = n
  }
  return min_e <= bounds.max_e_m && max_e >= bounds.min_e_m && min_n <= bounds.max_n_m && max_n >= bounds.min_n_m
}

/** SVG path data for a projected polyline, to one decimal. */
export function svgPathData(path: PointUTM[], project: (e_m: number, n_m: number) => [number, number]): string {
  return path
    .map(([e, n], i) => {
      const [x, y] = project(e, n)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join('')
}

/** (col, row) in design-grid cell space. */
export type CellPoint = [number, number]

export interface DesignGridContext {
  roads: { weight: Exclude<RoadWeight, 'path'>; name: string | null; points: CellPoint[] }[]
  buildings: CellPoint[][]
}

/** Roads and building rings within margin_m of the design grid, in its cell coordinates. Paths are left out. */
export function designGridContext(roads: BasemapWay[], buildings: PointUTM[][], design: DesignGrid, margin_m: number): DesignGridContext {
  const affine = affineFromDesignGrid(design)
  const bounds = expandBounds(gridBounds(affine, design.shape), margin_m)
  const toCells = (path: PointUTM[]) => path.map(([e, n]) => utmToCell(affine, e, n))
  return {
    roads: roads.flatMap((way) => {
      const weight = roadWeight(way.kind)
      return weight !== 'path' && pathTouches(way.path, bounds) ? [{ weight, name: way.name, points: toCells(way.path) }] : []
    }),
    buildings: buildings.filter((ring) => pathTouches(ring, bounds)).map(toCells),
  }
}
