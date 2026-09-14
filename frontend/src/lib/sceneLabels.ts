// Which names the 3D scene shows, and where they may sit on the ground, in UTM metres. Pure; projection to the
// screen, choosing a candidate position and collision happen per frame in src/scene/SceneLabels.tsx. Labels are
// chrome, never data.

import type { BasemapFeature, BasemapWay, DesignGrid, PointUTM } from '../types/contracts.ts'
import { designGridContext } from './basemap.ts'
import { affineFromDesignGrid, cellToUtm } from './geometry.ts'
import { crossStreetCrossings, roadRank } from './labels.ts'

export type SceneLabelKind = 'street' | 'cross' | 'road' | 'place'

export interface SceneLabelPosition {
  anchor: PointUTM
  /** A second point along the feature, so the label can turn to follow it; null for upright place names. */
  toward: PointUTM | null
}

export interface SceneLabel {
  text: string
  kind: SceneLabelKind
  /** Positions to try, best first. The projector uses the first that is on screen and collides with nothing. */
  candidates: SceneLabelPosition[]
}

export interface SceneLabelOptions {
  radius_m: number
  maxCrossStreets: number
  maxRoads: number
  maxPlaces: number
  maxRoadRank: number
}

/** Cross streets are looked for this far outside the design grid. */
const CROSS_SEARCH_MARGIN_M = 10
/** A cross street's name sits this many cells outside the grid, clear of the planted pits. */
const CROSS_LABEL_OFFSET_CELLS = 3
/** Long straight ways are sampled at this spacing, so a road crossing the view between two far vertices still counts. */
const DENSIFY_STEP_M = 25
/** Candidate positions along a road are this far apart, and at most this many are tried. */
const ROAD_CANDIDATE_SPACING_M = 50
const ROAD_CANDIDATES_MAX = 8
/** Fractions of the design street's length where its own name may sit. */
const STREET_CANDIDATE_ROWS = [0.2, 0.5, 0.8, 0.35, 0.65]

function length(points: PointUTM[]): number {
  let total = 0
  for (let i = 1; i < points.length; i++) total += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
  return total
}

function densify(path: PointUTM[], step_m: number): PointUTM[] {
  const out: PointUTM[] = []
  for (let i = 1; i < path.length; i++) {
    const [e0, n0] = path[i - 1]
    const [e1, n1] = path[i]
    const pieces = Math.max(1, Math.ceil(Math.hypot(e1 - e0, n1 - n0) / step_m))
    for (let k = 0; k < pieces; k++) out.push([e0 + ((e1 - e0) * k) / pieces, n0 + ((n1 - n0) * k) / pieces])
  }
  if (path.length > 0) out.push(path[path.length - 1])
  return out
}

/** Points roughly every spacing_m along a densified run, each with the next point for direction, nearest the centre first. */
function roadCandidates(points: PointUTM[], centre: PointUTM, spacing_m: number, max: number): SceneLabelPosition[] {
  const every = Math.max(1, Math.round(spacing_m / DENSIFY_STEP_M))
  const positions: SceneLabelPosition[] = []
  for (let i = 0; i < points.length - 1; i += every) positions.push({ anchor: points[i], toward: points[i + 1] })
  const distance = ([e, n]: PointUTM) => Math.hypot(e - centre[0], n - centre[1])
  return positions.sort((a, b) => distance(a.anchor) - distance(b.anchor)).slice(0, max)
}

/**
 * Names for the 3D scene, most important first: the design street along its centreline, its nearest cross streets
 * just outside the grid, other named roads by class and length within radius_m of the grid centre, then the
 * largest named buildings within the same radius.
 */
export function sceneLabels(
  roads: BasemapWay[],
  features: BasemapFeature[],
  design: DesignGrid,
  street: { osmName: string; label: string },
  options: SceneLabelOptions,
): SceneLabel[] {
  const [rows, cols] = design.shape
  const affine = affineFromDesignGrid(design)
  const centre = cellToUtm(affine, cols / 2, rows / 2)
  const near = ([e, n]: PointUTM) => Math.hypot(e - centre[0], n - centre[1]) <= options.radius_m

  const labels: SceneLabel[] = [
    {
      text: street.label,
      kind: 'street',
      candidates: STREET_CANDIDATE_ROWS.map((f) => ({
        anchor: cellToUtm(affine, cols / 2, rows * f),
        toward: cellToUtm(affine, cols / 2, rows * f + 10),
      })),
    },
  ]
  const used = new Set([street.label, street.osmName])

  const context = designGridContext(roads, [], design, CROSS_SEARCH_MARGIN_M)
  for (const crossing of crossStreetCrossings(context.roads, design.shape, street.osmName)) {
    if (labels.length > options.maxCrossStreets || used.has(crossing.name)) continue
    const sides = crossing.edge === 'near' ? [-1, 1] : [1, -1]
    labels.push({
      text: crossing.name,
      kind: 'cross',
      candidates: sides.map((side) => {
        const outside = side < 0 ? -CROSS_LABEL_OFFSET_CELLS : cols + CROSS_LABEL_OFFSET_CELLS
        return { anchor: cellToUtm(affine, outside, crossing.row), toward: cellToUtm(affine, outside + side * 5, crossing.row) }
      }),
    })
    used.add(crossing.name)
  }

  const best = new Map<string, { rank: number; length: number; points: PointUTM[] }>()
  for (const way of roads) {
    if (!way.name || used.has(way.name)) continue
    const rank = roadRank(way.kind)
    if (rank === null || rank > options.maxRoadRank) continue
    let run: PointUTM[] = []
    const runs: PointUTM[][] = []
    for (const point of densify(way.path, DENSIFY_STEP_M)) {
      if (near(point)) run.push(point)
      else {
        if (run.length >= 2) runs.push(run)
        run = []
      }
    }
    if (run.length >= 2) runs.push(run)
    for (const points of runs) {
      const current = best.get(way.name)
      const runLength = length(points)
      if (!current || rank < current.rank || (rank === current.rank && runLength > current.length)) {
        best.set(way.name, { rank, length: runLength, points })
      }
    }
  }
  const roadLabels = [...best.entries()]
    .sort(([, a], [, b]) => a.rank - b.rank || b.length - a.length)
    .slice(0, options.maxRoads)
    .map(([text, road]): SceneLabel => ({
      text,
      kind: 'road',
      candidates: roadCandidates(road.points, centre, ROAD_CANDIDATE_SPACING_M, ROAD_CANDIDATES_MAX),
    }))

  const placeLabels = features
    .filter((feature) => near(feature.anchor) && !used.has(feature.name))
    .slice(0, options.maxPlaces)
    .map((feature): SceneLabel => ({ text: feature.name, kind: 'place', candidates: [{ anchor: feature.anchor, toward: null }] }))

  return [...labels, ...roadLabels, ...placeLabels]
}
