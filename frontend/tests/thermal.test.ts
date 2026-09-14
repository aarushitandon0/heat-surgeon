import assert from 'node:assert/strict'
import { test } from 'node:test'
import { gridDomain, lerpGrid, normalise, paintGrid, parseHexColor, rampColor, type RGB } from '../src/lib/thermal.ts'

test('parseHexColor reads six and three digit forms', () => {
  // --t-00 in tokens.css: 1b = 27, 4b = 75, 57 = 87
  assert.deepEqual(parseHexColor('#1b4b57'), [27, 75, 87])
  assert.deepEqual(parseHexColor(' #fff '), [255, 255, 255])
  assert.throws(() => parseHexColor('var(--t-00)'))
})

test('rampColor interpolates linearly between evenly spaced stops', () => {
  const stops: RGB[] = [
    [0, 0, 0],
    [100, 200, 40],
    [200, 200, 200],
  ]
  assert.deepEqual(rampColor(stops, 0), [0, 0, 0])
  assert.deepEqual(rampColor(stops, 0.25), [50, 100, 20])
  assert.deepEqual(rampColor(stops, 0.5), [100, 200, 40])
  assert.deepEqual(rampColor(stops, 0.75), [150, 200, 120])
  assert.deepEqual(rampColor(stops, 1), [200, 200, 200])
  assert.deepEqual(rampColor(stops, 1.5), [200, 200, 200])
  assert.deepEqual(rampColor(stops, -1), [0, 0, 0])
})

test('normalise maps the domain to [0, 1] and a flat domain to the middle', () => {
  assert.equal(normalise(40, { min_c: 36, max_c: 44 }), 0.5)
  assert.equal(normalise(36, { min_c: 36, max_c: 44 }), 0)
  assert.equal(normalise(41, { min_c: 41, max_c: 41 }), 0.5)
})

test('gridDomain spans every non-null cell of every grid', () => {
  assert.deepEqual(gridDomain([[1, null], [3, 2]], [[-2]]), { min_c: -2, max_c: 3 })
  assert.equal(gridDomain([[null]]), null)
})

test('lerpGrid interpolates cell-wise and keeps nulls', () => {
  assert.deepEqual(lerpGrid([[36, null, 40]], [[34, 30, null]], 0.25), [[35.5, null, null]])
})

test('paintGrid writes one RGBA pixel per cell, row-major, transparent where null', () => {
  const stops: RGB[] = [
    [0, 0, 0],
    [200, 100, 50],
  ]
  const bytes = paintGrid(
    [
      [36, null],
      [44, 40],
    ],
    { min_c: 36, max_c: 44 },
    stops,
  )
  assert.deepEqual([...bytes], [0, 0, 0, 255, 0, 0, 0, 0, 200, 100, 50, 255, 100, 50, 25, 255])
})
