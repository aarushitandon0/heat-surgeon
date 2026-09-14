import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  formatBand,
  formatDeltaBand,
  formatInrRange,
  formatLatitude,
  formatNumber,
  formatOverpass,
  formatSeasons,
  formatSigned,
  roundSignificant,
} from '../src/lib/format.ts'

const MINUS = '−'

test('formatNumber uses a true minus and drops the sign on values that round to zero', () => {
  assert.equal(formatNumber(-1.2345, 2), `${MINUS}1.23`)
  assert.equal(formatNumber(-0.004, 2), '0.00')
  assert.equal(formatNumber(40.57, 1), '40.6')
})

test('formatSigned adds a plus to positive values', () => {
  assert.equal(formatSigned(2.293548, 2), '+2.29')
  assert.equal(formatSigned(-0.7455635933608128, 2), `${MINUS}0.75`)
  assert.equal(formatSigned(0.001, 2), '0.00')
})

test('formatDeltaBand lists the more-cooling end first and collapses equal ends', () => {
  // FC Road GA result, 2026-09-14: -1.3606 to -0.7456 °C
  assert.equal(formatDeltaBand(-1.3606385933608125, -0.7455635933608128), `${MINUS}1.36 to ${MINUS}0.75`)
  assert.equal(formatDeltaBand(-1.001, -0.999), `${MINUS}1.00`)
})

test('formatBand joins unsigned ends with an en dash', () => {
  assert.equal(formatBand(5, 27, 1), '5.0–27.0')
  assert.equal(formatBand(38.66, 38.64, 1), '38.7–38.6')
})

test('roundSignificant rounds outward on request', () => {
  assert.equal(roundSignificant(74400, 2, 'floor'), 74000)
  assert.equal(roundSignificant(118040, 2, 'ceil'), 120000)
  assert.equal(roundSignificant(7440, 2, 'ceil'), 7500)
  // An exact value stays put rather than stepping up on float noise.
  assert.equal(roundSignificant(118000, 3, 'ceil'), 118000)
})

test('formatInrRange rounds ends outward, never shows a midpoint, and is null when unpriced', () => {
  // 20 trees at the RUIDP range of 3,720 to 5,902 rupees each: 74,400 to 1,18,040.
  assert.equal(formatInrRange(20 * 3720, 20 * 5902), '₹74,000–1,20,000')
  assert.equal(formatInrRange(250000, 260000), '₹2,50,000–2,60,000')
  assert.equal(formatInrRange(null, 5000), null)
  assert.equal(formatInrRange(5000, null), null)
})

test('formatSeasons summarises provenance months and years', () => {
  assert.equal(formatSeasons([3, 4, 5], ['2024-03-01', '2026-05-31']), 'Mar–May, 2024–2026')
  assert.equal(formatSeasons([4], ['2025-04-01', '2025-04-30']), 'Apr, 2025')
  assert.equal(formatSeasons([5, 3], ['2024-03-01', '2024-05-31']), 'Mar, May, 2024')
})

test('coordinates and overpass time', () => {
  assert.equal(formatLatitude(18.52287), '18.5229° N')
  assert.equal(formatOverpass('10:57'), '10:57 IST')
})
