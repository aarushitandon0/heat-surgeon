import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildingGeometry, mergedBuildings } from '../src/scene/buildingGeometry.ts'
import {
  designGridCentre,
  footprintShapePoints,
  graticuleOffset,
  groundQuad,
  interventionPositions,
  packHeatTexture,
  ringArea_m2,
  streetRotationY_rad,
  threeQuarterPose,
  utmToScene,
} from '../src/scene/frame.ts'
import type { Building, DesignGrid } from '../src/types/contracts.ts'

function close(actual: ArrayLike<number>, expected: number[], eps = 1e-6) {
  assert.equal(actual.length, expected.length)
  for (let i = 0; i < expected.length; i++) assert.ok(Math.abs(actual[i] - expected[i]) < eps, `index ${i}: ${actual[i]} vs ${expected[i]}`)
}

// 10 cells along bearing 0 (north) by 4 across (east), 2 m cells, origin corner at (1000, 5000).
const NORTH: DesignGrid = { crs: 'EPSG:32643', origin_e_m: 1000, origin_n_m: 5000, bearing_deg: 0, cell_size_m: 2, shape: [10, 4] }

test('the scene origin is the design grid centre and north is -z', () => {
  const origin = designGridCentre(NORTH)
  close([origin.e_m, origin.n_m], [1004, 5010])
  close(utmToScene(origin, 1004, 5020), [0, -10])
  close(utmToScene(origin, 1014, 5010), [10, 0])
})

test('footprint points drop the closing duplicate and keep north as +y before rotation', () => {
  const origin = { e_m: 100, n_m: 200 }
  const ring: [number, number][] = [[100, 200], [110, 200], [110, 206], [100, 206], [100, 200]]
  assert.deepEqual(footprintShapePoints(ring, origin), [[0, 0], [10, 0], [10, 6], [0, 6]])
  assert.equal(ringArea_m2(footprintShapePoints(ring, origin)), 60)
})

test('a building extrudes up to its height and its north edge lands at -z', () => {
  const origin = { e_m: 100, n_m: 200 }
  const building: Building = {
    id: 'test', footprint: [[100, 200], [110, 200], [110, 206], [100, 206], [100, 200]],
    height_m: 9, height_source: 'estimated_from_area', footprint_source: 'OpenStreetMap',
  }
  const geometry = buildingGeometry(building, origin)!
  geometry.computeBoundingBox()
  const box = geometry.boundingBox!
  close([box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z], [0, 0, -6, 10, 9, 0])
  assert.equal(buildingGeometry({ ...building, footprint: [[0, 0], [1, 1], [0, 0]] }, origin), null)
  assert.equal(mergedBuildings([building, building], origin)!.getAttribute('position').count, 2 * geometry.getAttribute('position').count)
})

test('packHeatTexture writes value and validity per cell, row-major', () => {
  close(packHeatTexture([[36.5, null], [40, 41]]), [36.5, 1, 0, 0, 40, 1, 41, 1])
})

test('the ground quad spans the design grid corners with u across and v along', () => {
  const origin = designGridCentre(NORTH)
  const { positions, uvs } = groundQuad(NORTH, origin, 0.05)
  // Corners (col, row): (0,0) SW, (4,0) SE, (4,10) NE, (0,10) NW.
  close(positions, [-4, 0.05, 10, 4, 0.05, 10, 4, 0.05, -10, -4, 0.05, -10])
  close(uvs, [0, 0, 1, 0, 1, 1, 0, 1])
})

test('intervention markers sit at cell centres', () => {
  const origin = designGridCentre(NORTH)
  const { trees, coated } = interventionPositions(NORTH, [
    { type: 'tree', cells: [[0, 0]] },
    { type: 'reflective_pavement', cells: [[9, 3]] },
  ], origin)
  // Cell [0, 0] centre is E 1001, N 5001; cell [9, 3] centre is E 1007, N 5019.
  close(trees[0], [-3, 9])
  close(coated[0], [3, -9])
})

test('street rotation turns local +x onto the right of the street', () => {
  // Bearing 90 (east): right of the street is south, which is +z. Rotating +x by theta about +y gives (cos, -sin).
  const theta = streetRotationY_rad({ ...NORTH, bearing_deg: 90 })
  close([Math.cos(theta), -Math.sin(theta)], [0, 1])
})

test('graticule offset lands lines on UTM multiples', () => {
  // 377672.5 = 7553 * 50 + 22.5, so scene x = 27.5 is E 377700. 2048042.7 mod 50 = 42.7.
  close(graticuleOffset({ e_m: 377672.5, n_m: 2048042.7 }, 50), [27.5, 42.7], 1e-6)
})

test('three-quarter pose: right of the street, turned back, raised', () => {
  // Bearing 0: right is east (+x), back along the street is south (+z).
  const side = threeQuarterPose(NORTH, { azimuth_deg: 0, elevation_deg: 0, distance_m: 100 })
  close(side.position, [100, 0, 0])
  const back = threeQuarterPose(NORTH, { azimuth_deg: 90, elevation_deg: 0, distance_m: 100 })
  close(back.position, [0, 0, 100])
  // 45 degrees up at distance 100: height and horizontal reach are both 100 / sqrt 2.
  const raised = threeQuarterPose(NORTH, { azimuth_deg: 0, elevation_deg: 45, distance_m: 100 })
  close(raised.position, [100 / Math.SQRT2, 100 / Math.SQRT2, 0])
})
