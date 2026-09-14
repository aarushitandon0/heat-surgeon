// Grid geometry in UTM metres, and the fit of a UTM extent onto a north-up screen.
//
// Both grid kinds reduce to one affine from a cell corner (col, row) to (easting, northing):
//   ThermalGrid.transform  rasterio [a, b, c, d, e, f]: E = a*col + b*row + c, N = d*col + e*row + f
//   DesignGrid             rows advance along bearing_deg, columns to the right of it

import type { AffineUTM, DesignGrid, GridShape, PointUTM } from '../types/contracts.ts'

export interface CellAffine {
  origin_e_m: number
  origin_n_m: number
  e_per_col_m: number
  e_per_row_m: number
  n_per_col_m: number
  n_per_row_m: number
}

export interface BoundsUTM {
  min_e_m: number
  max_e_m: number
  min_n_m: number
  max_n_m: number
}

/** A north-up view: screen x grows east, screen y grows south. */
export interface View {
  scale_px_per_m: number
  offset_x_px: number
  offset_y_px: number
  min_e_m: number
  max_n_m: number
}

const DEG_TO_RAD = Math.PI / 180

export function affineFromTransform(transform: AffineUTM): CellAffine {
  const [a, b, c, d, e, f] = transform
  return { origin_e_m: c, origin_n_m: f, e_per_col_m: a, e_per_row_m: b, n_per_col_m: d, n_per_row_m: e }
}

export function affineFromDesignGrid(grid: DesignGrid): CellAffine {
  const bearing_rad = grid.bearing_deg * DEG_TO_RAD
  const sin = Math.sin(bearing_rad)
  const cos = Math.cos(bearing_rad)
  // Along the street is (sin, cos) in (E, N); to its right is (cos, -sin).
  return {
    origin_e_m: grid.origin_e_m,
    origin_n_m: grid.origin_n_m,
    e_per_col_m: grid.cell_size_m * cos,
    e_per_row_m: grid.cell_size_m * sin,
    n_per_col_m: -grid.cell_size_m * sin,
    n_per_row_m: grid.cell_size_m * cos,
  }
}

/**
 * The design grid in its own street frame, in metres: distance along the street to the right, distance
 * across it downward. Used to draw a long, thin segment legibly; not a geographic position.
 */
export function streetFrameAffine(grid: DesignGrid): CellAffine {
  return {
    origin_e_m: 0,
    origin_n_m: 0,
    e_per_col_m: 0,
    e_per_row_m: grid.cell_size_m,
    n_per_col_m: -grid.cell_size_m,
    n_per_row_m: 0,
  }
}

/** UTM position of a cell-space point; (col, row) = (0, 0) is the outer corner of cell [0, 0]. */
export function cellToUtm(affine: CellAffine, col: number, row: number): PointUTM {
  return [
    affine.origin_e_m + affine.e_per_col_m * col + affine.e_per_row_m * row,
    affine.origin_n_m + affine.n_per_col_m * col + affine.n_per_row_m * row,
  ]
}

/** Fractional (col, row) of a UTM point. */
export function utmToCell(affine: CellAffine, e_m: number, n_m: number): [number, number] {
  const de_m = e_m - affine.origin_e_m
  const dn_m = n_m - affine.origin_n_m
  const det = affine.e_per_col_m * affine.n_per_row_m - affine.e_per_row_m * affine.n_per_col_m
  return [
    (affine.n_per_row_m * de_m - affine.e_per_row_m * dn_m) / det,
    (-affine.n_per_col_m * de_m + affine.e_per_col_m * dn_m) / det,
  ]
}

export function gridBounds(affine: CellAffine, shape: GridShape): BoundsUTM {
  const [rows, cols] = shape
  const corners = [cellToUtm(affine, 0, 0), cellToUtm(affine, cols, 0), cellToUtm(affine, 0, rows), cellToUtm(affine, cols, rows)]
  return {
    min_e_m: Math.min(...corners.map((p) => p[0])),
    max_e_m: Math.max(...corners.map((p) => p[0])),
    min_n_m: Math.min(...corners.map((p) => p[1])),
    max_n_m: Math.max(...corners.map((p) => p[1])),
  }
}

/** Largest north-up scale that fits the bounds inside the box with a margin, centred. */
export function fitView(bounds: BoundsUTM, width_px: number, height_px: number, margin_px: number): View {
  const span_e_m = bounds.max_e_m - bounds.min_e_m
  const span_n_m = bounds.max_n_m - bounds.min_n_m
  const usable_w_px = Math.max(1, width_px - 2 * margin_px)
  const usable_h_px = Math.max(1, height_px - 2 * margin_px)
  const scale_px_per_m = Math.min(usable_w_px / span_e_m, usable_h_px / span_n_m)
  return {
    scale_px_per_m,
    offset_x_px: (width_px - span_e_m * scale_px_per_m) / 2,
    offset_y_px: (height_px - span_n_m * scale_px_per_m) / 2,
    min_e_m: bounds.min_e_m,
    max_n_m: bounds.max_n_m,
  }
}

export function utmToScreen(view: View, e_m: number, n_m: number): [number, number] {
  return [
    view.offset_x_px + (e_m - view.min_e_m) * view.scale_px_per_m,
    view.offset_y_px + (view.max_n_m - n_m) * view.scale_px_per_m,
  ]
}

export function screenToUtm(view: View, x_px: number, y_px: number): PointUTM {
  return [
    view.min_e_m + (x_px - view.offset_x_px) / view.scale_px_per_m,
    view.max_n_m - (y_px - view.offset_y_px) / view.scale_px_per_m,
  ]
}

/**
 * Canvas setTransform arguments [a, b, c, d, e, f] that draw one pixel per cell, pixel (x, y) =
 * cell (col, row), at its true position and rotation in the view.
 */
export function cellCanvasTransform(view: View, affine: CellAffine): [number, number, number, number, number, number] {
  const s = view.scale_px_per_m
  return [
    s * affine.e_per_col_m,
    -s * affine.n_per_col_m,
    s * affine.e_per_row_m,
    -s * affine.n_per_row_m,
    view.offset_x_px + (affine.origin_e_m - view.min_e_m) * s,
    view.offset_y_px + (view.max_n_m - affine.origin_n_m) * s,
  ]
}

/** A 1, 2 or 5 × 10^k step giving roughly `target` intervals across the span. */
export function niceStep(span: number, target: number): number {
  const raw = span / target
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const normalised = raw / magnitude
  const factor = normalised < 1.5 ? 1 : normalised < 3.5 ? 2 : normalised < 7.5 ? 5 : 10
  return factor * magnitude
}

/** Multiples of step inside [min, max]. */
export function stepsWithin(min: number, max: number, step: number): number[] {
  const values: number[] = []
  for (let k = Math.ceil(min / step); k * step <= max; k++) values.push(k * step)
  return values
}
