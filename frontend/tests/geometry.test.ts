import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  affineFromDesignGrid,
  affineFromTransform,
  cellCanvasTransform,
  cellToUtm,
  fitView,
  gridBounds,
  niceStep,
  stepsWithin,
  streetFrameAffine,
  utmToCell,
  utmToScreen,
} from '../src/lib/geometry.ts'
import type { DesignGrid } from '../src/types/contracts.ts'

const EPS = 1e-9

function assertClose(actual: number[], expected: number[]) {
  assert.equal(actual.length, expected.length)
  actual.forEach((value, i) => assert.ok(Math.abs(value - expected[i]) < 1e-6, `index ${i}: ${value} vs ${expected[i]}`))
}

function designGrid(bearing_deg: number, origin_e_m = 100, origin_n_m = 200): DesignGrid {
  return { crs: 'EPSG:32643', origin_e_m, origin_n_m, bearing_deg, cell_size_m: 2, shape: [100, 20] }
}

test('a rasterio transform places row 0 at the north edge', () => {
  // FC Road window transform from the real ThermalGrid.
  const affine = affineFromTransform([30, 0, 376755, 0, -30, 2049165])
  assert.deepEqual(cellToUtm(affine, 1, 2), [376785, 2049105])
})

test('design grid rows run along the bearing and columns to its right', () => {
  // Bearing 0: rows go north, columns go east.
  assertClose(cellToUtm(affineFromDesignGrid(designGrid(0)), 1, 3), [102, 206])
  // Bearing 90: rows go east, columns go south.
  assertClose(cellToUtm(affineFromDesignGrid(designGrid(90)), 1, 3), [106, 198])
})

test('the street frame lays rows along x and columns down the screen', () => {
  const affine = streetFrameAffine(designGrid(352.3))
  // Row 3 is 6 m along the street; column 1 is 2 m across it, drawn below.
  assert.deepEqual(cellToUtm(affine, 1, 3), [6, -2])
  assert.deepEqual(gridBounds(affine, [100, 20]), { min_e_m: 0, max_e_m: 200, min_n_m: -40, max_n_m: 0 })
  assertClose(utmToCell(affine, 6.5, -2.5), [1.25, 3.25])
})

test('utmToCell inverts cellToUtm on a rotated grid', () => {
  const affine = affineFromDesignGrid(designGrid(352.30410075063276, 377672.5582386467, 2048042.6985135425))
  const [e_m, n_m] = cellToUtm(affine, 7.25, 63.5)
  assertClose(utmToCell(affine, e_m, n_m), [7.25, 63.5])
})

test('gridBounds covers the four corners', () => {
  assert.deepEqual(gridBounds(affineFromDesignGrid(designGrid(0, 0, 0)), [100, 20]), {
    min_e_m: 0,
    max_e_m: 40,
    min_n_m: 0,
    max_n_m: 200,
  })
})

test('fitView centres the extent at the largest scale that fits', () => {
  // Usable box 220 x 200 px; 40 x 200 m fits at 1 px/m, leaving 100 px each side horizontally.
  const view = fitView({ min_e_m: 0, max_e_m: 40, min_n_m: 0, max_n_m: 200 }, 240, 220, 10)
  assert.equal(view.scale_px_per_m, 1)
  assert.equal(view.offset_x_px, 100)
  assert.equal(view.offset_y_px, 10)
  assert.deepEqual(utmToScreen(view, 20, 100), [120, 110])
})

test('cellCanvasTransform lands a cell where cellToUtm and utmToScreen put it', () => {
  const view = fitView({ min_e_m: 0, max_e_m: 40, min_n_m: 0, max_n_m: 200 }, 240, 220, 10)
  const affine = affineFromDesignGrid(designGrid(90, 0, 100))
  const [a, b, c, d, e, f] = cellCanvasTransform(view, affine)
  // Cell-space (1, 3) is E 6, N 98, which is screen (106, 112).
  assertClose([a * 1 + c * 3 + e, b * 1 + d * 3 + f], [106, 112])
  assertClose(utmToScreen(view, ...cellToUtm(affine, 1, 3)), [106, 112])
  assert.ok(Math.abs(a) < EPS && Math.abs(d) < EPS)
})

test('niceStep picks 1, 2 or 5 times a power of ten', () => {
  assert.equal(niceStep(2010, 5), 500)
  assert.equal(niceStep(200, 8), 20)
  assert.equal(niceStep(100, 10), 10)
})

test('stepsWithin lists multiples inside the range', () => {
  assert.deepEqual(stepsWithin(-5, 12, 5), [-5, 0, 5, 10])
})
