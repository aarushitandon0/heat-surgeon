import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  CROWN_CHECK_TEXT,
  DECCAN_SPECIES,
  EXCLUDED_SPECIES,
  crownCheck,
  largestTrunkForPit,
  narrowestTreePit_m,
} from '../src/lib/species.ts'
import type { CrossSectionBand } from '../src/types/contracts.ts'

test('narrowestTreePit_m measures tree pit bands only', () => {
  const band = (kind: CrossSectionBand['kind'], from: number, to: number) =>
    ({ kind, offset_from_m: from, offset_to_m: to, plantable: kind === 'tree_pit' }) as CrossSectionBand
  // 24A-like: pits 1.0 m (-8.0 to -7.0) and 1.5 m (6.0 to 7.5); the carriageway is ignored.
  assert.equal(narrowestTreePit_m([band('tree_pit', -8, -7), band('carriageway', -7, 6), band('tree_pit', 6, 7.5)]), 1)
  assert.equal(narrowestTreePit_m([band('footway', -2, 0), band('carriageway', 0, 7)]), null)
})

test('largestTrunkForPit reads the USDG grate table, hand-checked', () => {
  // 1.0 m pit: the 0.75 m grate fits, the 1.5 m one does not, so trunks up to 0.3 m.
  assert.deepEqual(largestTrunkForPit(1.0), { trunk_diameter_max_m: 0.3, grate_side_m: 0.75 })
  // 1.5 m pit: exactly fits the 1.5 m grate, so trunks up to 0.9 m.
  assert.deepEqual(largestTrunkForPit(1.5), { trunk_diameter_max_m: 0.9, grate_side_m: 1.5 })
  // 2.5 m pit: the largest row, 1.2 m trunks on a 2 m grate.
  assert.deepEqual(largestTrunkForPit(2.5), { trunk_diameter_max_m: 1.2, grate_side_m: 2 })
  // 0.5 m: not even the 0.6 m grate fits.
  assert.equal(largestTrunkForPit(0.5), null)
})

test('crownCheck flags small trees and never confirms a match without a crown diameter', () => {
  assert.equal(crownCheck('small'), 'likely_smaller')
  assert.equal(crownCheck('large'), 'consistent_unconfirmed')
  assert.equal(crownCheck(null), 'not_checkable')
  assert.ok(CROWN_CHECK_TEXT.consistent_unconfirmed.includes('no crown diameter'))
})

test('every size carries the words it came from, and the Pune avoid list wins over the national list', () => {
  for (const s of DECCAN_SPECIES) assert.equal(s.size === null, s.size_quote === null, s.botanical_name)
  assert.ok(!DECCAN_SPECIES.some((s) => s.botanical_name.startsWith('Polyalthia')))
  assert.ok(EXCLUDED_SPECIES.some((s) => s.botanical_name.startsWith('Polyalthia')))
})
