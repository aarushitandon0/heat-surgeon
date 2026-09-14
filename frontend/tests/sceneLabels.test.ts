import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sceneLabels } from '../src/lib/sceneLabels.ts'
import type { BasemapFeature, DesignGrid } from '../src/types/contracts.ts'

// Bearing 0, 2 m cells, origin (0, 0), 100 rows by 20 columns: rows run 200 m north, columns 40 m east.
// Grid centre is (20, 100).
const DESIGN: DesignGrid = { crs: 'EPSG:32643', origin_e_m: 0, origin_n_m: 0, bearing_deg: 0, cell_size_m: 2, shape: [100, 20] }
const OPTIONS = { radius_m: 350, maxCrossStreets: 3, maxRoads: 8, maxPlaces: 4, maxRoadRank: 3 }

const feature = (name: string, anchor: [number, number]): BasemapFeature => ({ name, kind: 'yes', anchor, footprint_area_m2: 100 })

test('sceneLabels orders the street, its cross street, other roads, then places, and drops what is far away', () => {
  const labels = sceneLabels(
    [
      { kind: 'primary', name: 'Gopal Krushna Gokhale Path', path: [[20, -100], [20, 300]] },
      { kind: 'tertiary', name: 'Cross', path: [[-100, 100], [200, 100]] },
      { kind: 'primary', name: 'Main', path: [[-300, 300], [300, 300]] },
      { kind: 'primary', name: 'Far', path: [[5000, 0], [5100, 0]] },
      { kind: 'residential', name: 'Lane', path: [[-50, 50], [100, 50]] },
    ],
    [feature('Near hall', [60, 120]), feature('Far hall', [4000, 4000])],
    DESIGN,
    { osmName: 'Gopal Krushna Gokhale Path', label: 'FC Road' },
    OPTIONS,
  )
  // Cross streets are named whatever their class, like the 2D grid's: Lane (residential) crosses at row 25, further
  // from the middle (row 50) than Cross, so it comes second. Residential roads that do not cross are never named.
  assert.deepEqual(labels.map((l) => [l.kind, l.text]), [
    ['street', 'FC Road'],
    ['cross', 'Cross'],
    ['cross', 'Lane'],
    ['road', 'Main'],
    ['place', 'Near hall'],
  ])
  // The street's first candidate is on the centreline (column 10, e = 20 m) a fifth of the way along (row 20, n = 40 m).
  assert.deepEqual(labels[0].candidates[0].anchor, [20, 40])
  // Cross at row 50 meets the near edge first; its first candidate is 3 cells outside: column -3, e = -6 m, n = 100 m.
  // The second is 3 cells beyond the far edge: column 23, e = 46 m.
  assert.deepEqual(labels[1].candidates.map((c) => c.anchor), [[-6, 100], [46, 100]])
  // Main's candidates all lie on the road, nearest the grid centre (20, 100) first.
  const main = labels[3].candidates
  assert.ok(main.length > 1 && main.every((c) => c.anchor[1] === 300 && c.toward !== null))
  const distance = (c: (typeof main)[number]) => Math.hypot(c.anchor[0] - 20, c.anchor[1] - 100)
  assert.ok(main.every((c, i) => i === 0 || distance(main[i - 1]) <= distance(c)))
  assert.deepEqual(labels[4].candidates, [{ anchor: [60, 120], toward: null }])
})
