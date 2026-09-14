// Scene framing for the 3D view. Pure functions, no three.js, so they are testable in node.
//
// Scene axes: x east, y up, z south, in metres from an origin at the design grid centre. UTM
// coordinates are about 2 million metres; subtracting the origin keeps GPU floats free of jitter.

import { affineFromDesignGrid, cellToUtm } from '../lib/geometry.ts'
import type { Grid } from '../lib/thermal.ts'
import type { DesignGrid, Intervention, PointUTM } from '../types/contracts.ts'

export interface SceneOrigin {
  e_m: number
  n_m: number
}

const DEG_TO_RAD = Math.PI / 180

export function designGridCentre(grid: DesignGrid): SceneOrigin {
  const [rows, cols] = grid.shape
  const [e_m, n_m] = cellToUtm(affineFromDesignGrid(grid), cols / 2, rows / 2)
  return { e_m, n_m }
}

/** [x, z] in scene metres. North is -z. */
export function utmToScene(origin: SceneOrigin, e_m: number, n_m: number): [number, number] {
  return [e_m - origin.e_m, -(n_m - origin.n_m)]
}

/**
 * A footprint ring as 2D shape points (x east, y north) for THREE.Shape, closing duplicate dropped.
 * The extrusion runs along +z and is then rotated -90° about x, which sends +z up and +y (north) to -z.
 */
export function footprintShapePoints(footprint: PointUTM[], origin: SceneOrigin): [number, number][] {
  const points = footprint.map(([e_m, n_m]) => [e_m - origin.e_m, n_m - origin.n_m] as [number, number])
  const first = points[0]
  const last = points[points.length - 1]
  if (points.length > 1 && first[0] === last[0] && first[1] === last[1]) points.pop()
  return points
}

/** Signed shoelace area of a ring in square metres. */
export function ringArea_m2(points: [number, number][]): number {
  let twice = 0
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i]
    const [x1, y1] = points[(i + 1) % points.length]
    twice += x0 * y1 - x1 * y0
  }
  return twice / 2
}

/**
 * Before and after grids as one four-channel float texture for the reveal, row-major: texel (x = col, y = row)
 * holds [before °C, after °C, 1, 0] where both grids have a value and [0, 0, 0, 0] otherwise, so the shader
 * can interpolate between the two on the GPU without re-uploading anything while the reveal plays.
 */
export function packRevealTexture(before: Grid, after: Grid): Float32Array {
  const rows = before.length
  const cols = rows === 0 ? 0 : before[0].length
  const data = new Float32Array(rows * cols * 4)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const from = before[r][c]
      const to = after[r]?.[c] ?? null
      if (from === null || to === null) continue
      const i = (r * cols + c) * 4
      data[i] = from
      data[i + 1] = to
      data[i + 2] = 1
    }
  }
  return data
}

/** The design grid as one quad: four corner positions (x, y, z) and their UVs, u across and v along the street. */
export function groundQuad(grid: DesignGrid, origin: SceneOrigin, y_m: number): { positions: Float32Array; uvs: Float32Array } {
  const [rows, cols] = grid.shape
  const affine = affineFromDesignGrid(grid)
  const corners: [number, number][] = [
    [0, 0],
    [cols, 0],
    [cols, rows],
    [0, rows],
  ]
  const positions = new Float32Array(12)
  const uvs = new Float32Array(8)
  corners.forEach(([col, row], i) => {
    const [x, z] = utmToScene(origin, ...cellToUtm(affine, col, row))
    positions.set([x, y_m, z], i * 3)
    uvs.set([col / cols, row / rows], i * 2)
  })
  return { positions, uvs }
}

/** Scene [x, z] of each intervention cell centre, by type. */
export function interventionPositions(grid: DesignGrid, interventions: Intervention[], origin: SceneOrigin) {
  const affine = affineFromDesignGrid(grid)
  const place = (cells: [number, number][]) =>
    cells.map(([row, col]) => utmToScene(origin, ...cellToUtm(affine, col + 0.5, row + 0.5)))
  return {
    trees: place(interventions.filter((iv) => iv.type === 'tree').flatMap((iv) => iv.cells)),
    coated: place(interventions.filter((iv) => iv.type !== 'tree').flatMap((iv) => iv.cells)),
  }
}

/** Rotation about +y that turns local +x onto the direction to the right of the street. */
export function streetRotationY_rad(grid: DesignGrid): number {
  return -grid.bearing_deg * DEG_TO_RAD
}

/** Offset for a scene-aligned grid so its lines fall on UTM multiples of step_m. */
export function graticuleOffset(origin: SceneOrigin, step_m: number): [number, number] {
  const mod = (value: number) => ((value % step_m) + step_m) % step_m
  return [mod(-origin.e_m), mod(origin.n_m)]
}

export interface CameraPose {
  position: [number, number, number]
  target: [number, number, number]
}

export interface ThreeQuarterView {
  /** Horizontal angle from the street's right-hand perpendicular, back towards the start of the segment. */
  azimuth_deg: number
  /** Angle above the ground plane. */
  elevation_deg: number
  distance_m: number
}

/** A camera on the right of the street, turned back along it and raised, looking at the design grid centre. */
export function threeQuarterPose(grid: DesignGrid, view: ThreeQuarterView): CameraPose {
  const bearing_rad = grid.bearing_deg * DEG_TO_RAD
  const azimuth_rad = view.azimuth_deg * DEG_TO_RAD
  const elevation_rad = view.elevation_deg * DEG_TO_RAD
  // In scene (x, z): along the street is (sin b, -cos b); to its right is (cos b, sin b).
  const dirX = Math.cos(bearing_rad) * Math.cos(azimuth_rad) - Math.sin(bearing_rad) * Math.sin(azimuth_rad)
  const dirZ = Math.sin(bearing_rad) * Math.cos(azimuth_rad) + Math.cos(bearing_rad) * Math.sin(azimuth_rad)
  const horizontal_m = view.distance_m * Math.cos(elevation_rad)
  return {
    position: [dirX * horizontal_m, view.distance_m * Math.sin(elevation_rad), dirZ * horizontal_m],
    target: [0, 0, 0],
  }
}
