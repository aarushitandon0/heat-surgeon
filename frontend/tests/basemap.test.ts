import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cityWayClass, designGridContext, expandBounds, pathTouches, roadWeight, svgPathData } from '../src/lib/basemap.ts'
import { formatCountRange } from '../src/lib/format.ts'
import { coolingMarginPercent, countRange, paddedDomain } from '../src/lib/model.ts'
import type { ComparisonArm, DesignGrid } from '../src/types/contracts.ts'

test('roadWeight and cityWayClass sort OSM values', () => {
  assert.equal(roadWeight('primary'), 'major')
  assert.equal(roadWeight('secondary_link'), 'major')
  assert.equal(roadWeight('residential'), 'minor')
  assert.equal(roadWeight('footway'), 'path')
  assert.equal(cityWayClass('river'), 'river')
  assert.equal(cityWayClass('trunk'), 'major')
  assert.equal(cityWayClass('secondary'), 'minor')
})

test('pathTouches keeps a path whose box crosses the bounds, even with no vertex inside', () => {
  const bounds = { min_e_m: 0, max_e_m: 10, min_n_m: 0, max_n_m: 10 }
  assert.equal(pathTouches([[-5, 5], [15, 5]], bounds), true)
  assert.equal(pathTouches([[20, 20], [30, 30]], bounds), false)
  assert.deepEqual(expandBounds(bounds, 2), { min_e_m: -2, max_e_m: 12, min_n_m: -2, max_n_m: 12 })
})

test('svgPathData projects and rounds to one decimal', () => {
  assert.equal(svgPathData([[1, 2], [3.25, 4]], (e, n) => [e, -n]), 'M1.0 -2.0L3.3 -4.0')
})

test('designGridContext places UTM points in cell space and drops far geometry', () => {
  // Bearing 0, 2 m cells, origin at (0, 0): columns advance east, rows advance north.
  const design: DesignGrid = { crs: 'EPSG:32643', origin_e_m: 0, origin_n_m: 0, bearing_deg: 0, cell_size_m: 2, shape: [10, 5] }
  const context = designGridContext(
    [
      { kind: 'residential', name: null, path: [[4, 6], [4, 16]] },
      { kind: 'footway', name: null, path: [[2, 2], [4, 4]] },
      { kind: 'primary', name: null, path: [[1000, 1000], [1010, 1000]] },
    ],
    [[[0, 0], [2, 0], [2, 2], [0, 0]]],
    design,
    5,
  )
  assert.equal(context.roads.length, 1)
  assert.equal(context.roads[0].weight, 'minor')
  // (e, n) = (4, 6) is 2 cells east and 3 cells north: (col, row) = (2, 3).
  assert.deepEqual(context.roads[0].points, [[2, 3], [2, 8]])
  assert.deepEqual(context.buildings[0][1], [1, 0])
})

const arm = (high_c: number, trees = 20): ComparisonArm => ({
  temp_delta_c_low: high_c,
  temp_delta_c_high: high_c,
  cost_inr_low: null,
  cost_inr_high: null,
  unpriced_interventions: [],
  trees,
  reflective_cells: 0,
})

test('coolingMarginPercent compares conservative ends, hand-checked', () => {
  // -0.90 against -0.80: 0.90 / 0.80 - 1 = 12.5% more cooling.
  assert.ok(Math.abs(coolingMarginPercent(arm(-0.9), arm(-0.8))! - 12.5) < 1e-9)
  // -0.70 against -0.80: 12.5% less.
  assert.ok(Math.abs(coolingMarginPercent(arm(-0.7), arm(-0.8))! + 12.5) < 1e-9)
  assert.equal(coolingMarginPercent(arm(-0.7), arm(0)), null)
})

test('countRange and formatCountRange state counts plainly', () => {
  assert.deepEqual(countRange([26, 25, 26, 26]), [25, 26])
  assert.equal(formatCountRange([25, 26]), '25–26')
  assert.equal(formatCountRange([150, 150]), '150')
})

test('paddedDomain pads by a fraction of the span, with a floor', () => {
  // span 0.2, 10% = 0.02
  const [lo, hi] = paddedDomain([-0.8, -0.6, -0.7], 0.1, 0.01)
  assert.ok(Math.abs(lo + 0.82) < 1e-9 && Math.abs(hi + 0.58) < 1e-9)
  // flat curve: floor of 0.02 either side
  assert.deepEqual(paddedDomain([-0.5, -0.5], 0.1, 0.02), [-0.52, -0.48])
})
