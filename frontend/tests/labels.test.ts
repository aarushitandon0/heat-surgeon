import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  boxesOverlap,
  cityLabelCandidates,
  crossStreetCrossings,
  designGridLabels,
  placeOnPath,
  placePointLabels,
  roadCandidates,
  rotatedBox,
  uprightAngle,
} from '../src/lib/labels.ts'
import type { BasemapWay } from '../src/types/contracts.ts'

const near = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} vs ${b}`)
/** Every character 6 units wide. */
const measure = (text: string) => text.length * 6

test('uprightAngle never leaves text upside down', () => {
  near(uprightAngle(Math.PI), 0)
  near(uprightAngle((3 * Math.PI) / 4), -Math.PI / 4)
  near(uprightAngle((-3 * Math.PI) / 4), Math.PI / 4)
  near(uprightAngle(Math.PI / 2), Math.PI / 2)
})

test('placeOnPath centres a label on a straight stretch, reading left to right either way the path runs', () => {
  const east = placeOnPath([[0, 0], [100, 0]], 20, [0.5], 3)!
  assert.deepEqual([east.x, east.y], [50, 0])
  near(east.angle_rad, 0)
  const west = placeOnPath([[100, 0], [0, 0]], 20, [0.5], 3)!
  near(west.angle_rad, 0)
})

test('placeOnPath refuses a bend under the label and a path shorter than it', () => {
  // L-shaped: at the middle the label would span (30, 0) to (50, 20), a chord of 28 against a width of 40.
  assert.equal(placeOnPath([[0, 0], [50, 0], [50, 50]], 40, [0.5], 3), null)
  assert.equal(placeOnPath([[0, 0], [10, 0]], 20, [0.5], 3), null)
})

test('rotatedBox bounds a rotated rectangle', () => {
  // 20 by 10 turned 90°: 10 wide, 20 tall, plus pad 1 each side.
  const box = rotatedBox(0, 0, 20, 10, Math.PI / 2, 1)
  near(box.w, 12, 1e-9)
  near(box.h, 22, 1e-9)
})

test('placePointLabels drops a label that would collide, and tries the next anchor', () => {
  const bounds = { x: 0, y: 0, w: 200, h: 100 }
  const placed = placePointLabels(
    [
      { text: 'Aaaa', anchors: [{ x: 50, y: 50, align: 'center' }] },
      { text: 'Bbbb', anchors: [{ x: 52, y: 50, align: 'center' }, { x: 150, y: 50, align: 'center' }] },
      { text: 'Cccc', anchors: [{ x: 51, y: 51, align: 'center' }] },
    ],
    measure,
    12,
    bounds,
    [],
    10,
    2,
  )
  assert.deepEqual(placed.map((l) => [l.text, l.x]), [['Aaaa', 50], ['Bbbb', 150]])
  assert.equal(boxesOverlap(placed[0].box, placed[1].box), false)
})

test('roadCandidates puts the design street first under its display name, then major roads by class', () => {
  const way = (kind: string, name: string | null, x = 0): BasemapWay => ({ kind, name, path: [[x, 0], [x + 100, 0]] })
  const candidates = roadCandidates(
    [way('tertiary', 'Lane'), way('primary', 'Karve Road'), way('primary', 'Gopal Krushna Gokhale Path'), way('residential', 'Small'), way('primary', null)],
    (e, n) => [e, n],
    3,
    { osmName: 'Gopal Krushna Gokhale Path', label: 'FC Road' },
  )
  assert.deepEqual(candidates.map((c) => c.text), ['FC Road', 'Karve Road', 'Lane'])
})

test('crossStreetCrossings keeps a road that carries its OSM class only down to tertiary', () => {
  // All three cross the far line (column 21) at row 50; only the classes differ.
  const road = (name: string, kind?: string) => ({ name, kind, points: [[-5, 50], [25, 50]] as [number, number][] })
  const crossings = crossStreetCrossings(
    [road('Tertiary Road', 'tertiary'), road('Lane 3', 'residential'), road('Service lane', 'service'), road('Unclassified')],
    [100, 20],
    'Street',
  )
  assert.deepEqual(crossings.map((c) => c.name).sort(), ['Tertiary Road', 'Unclassified'])
})

test('crossStreetCrossings finds where a road meets the lines one column outside each long edge, nearest the middle', () => {
  // Grid 100 rows by 20 columns; lines at column -1 and 21. Road from (col -5, row 30) to (col 25, row 34):
  //   column -1 at t = 4/30, row 30 + 4 * 4/30 = 30.533; column 21 at t = 26/30, row 33.467 (nearer row 50).
  const crossings = crossStreetCrossings(
    [
      { name: 'Cross', points: [[-5, 30], [25, 34]] },
      { name: 'Street', points: [[-5, 10], [25, 10]] },
      { name: 'Far away', points: [[-5, 200], [25, 200]] },
    ],
    [100, 20],
    'Street',
  )
  assert.equal(crossings.length, 1)
  assert.equal(crossings[0].edge, 'far')
  near(crossings[0].row, 30 + (4 * 26) / 30, 1e-9)
})

test('designGridLabels names the street and places a cross street beside the edge it meets', () => {
  const labels = designGridLabels(
    [{ name: 'Cross', points: [[-5, 50], [25, 50]] }],
    [100, 20],
    (col, row) => [row * 4, col * 4 + 100],
    { osmName: 'Street', label: 'FC Road' },
    measure,
    12,
    { x: 0, y: 0, w: 400, h: 400 },
    { gap: 6, pad: 2, maxCrossStreets: 3, inward: false },
  )
  assert.deepEqual(labels.map((l) => l.text), ['FC Road', 'Cross'])
  // Crossing at row 50 on the near edge (drawn y = 100): label centred at x = 200, 6 + 6 above the edge.
  assert.deepEqual([labels[1].x, labels[1].y], [200, 88])
})

test('cityLabelCandidates lists rivers before trunk roads and ignores what lies outside the extent', () => {
  const candidates = cityLabelCandidates(
    [
      { kind: 'trunk', name: 'Nagar Road', path: [[0, 0], [50, 0], [90, 0]] },
      { kind: 'river', name: 'Mutha', path: [[10, 10], [20, 10], [30, 10]] },
      { kind: 'primary', name: 'Minor', path: [[10, 20], [60, 20]] },
      { kind: 'river', name: 'Elsewhere', path: [[500, 500], [600, 500]] },
    ],
    [-1, -1, 100, 100],
  )
  assert.deepEqual(candidates.map((c) => c.text), ['Mutha', 'Nagar Road'])
})
