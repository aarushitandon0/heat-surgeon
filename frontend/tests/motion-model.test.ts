import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DECODE_CHAR_MS, easeInOutCubic, lockedChars } from '../src/lib/motion.ts'
import { budgetMatched, contrastAgainst } from '../src/lib/model.ts'
import type { Comparison, ComparisonArm, SurfaceContrast } from '../src/types/contracts.ts'

test('easeInOutCubic hits its hand-computed values', () => {
  assert.equal(easeInOutCubic(0), 0)
  assert.equal(easeInOutCubic(0.25), 0.0625) // 4 * 0.25^3
  assert.equal(easeInOutCubic(0.5), 0.5)
  assert.equal(easeInOutCubic(0.75), 0.9375) // 1 - 0.5^3 / 2
  assert.equal(easeInOutCubic(1), 1)
  assert.equal(easeInOutCubic(2), 1)
})

test('lockedChars locks one character per DECODE_CHAR_MS, starting on arrival', () => {
  assert.equal(lockedChars(-1, 5), 0)
  assert.equal(lockedChars(0, 5), 1)
  assert.equal(lockedChars(DECODE_CHAR_MS, 5), 2)
  assert.equal(lockedChars(10_000, 5), 5)
})

// FC Road calibration contrasts, 2026-09-14.
const CONTRASTS: SurfaceContrast[] = [
  { class_a: 'canopy', class_b: 'paved', difference_c: -5.683228453723135, standard_error_c: 1.1113094538481165 },
  { class_a: 'paved', class_b: 'bare', difference_c: -2.293548100045584, standard_error_c: 1.170766372344379 },
]

test('contrastAgainst reads a pair in either order, flipping the sign only', () => {
  assert.deepEqual(contrastAgainst(CONTRASTS, 'canopy', 'paved'), { difference_c: -5.683228453723135, standard_error_c: 1.1113094538481165 })
  assert.deepEqual(contrastAgainst(CONTRASTS, 'bare', 'paved'), { difference_c: 2.293548100045584, standard_error_c: 1.170766372344379 })
  assert.equal(contrastAgainst(CONTRASTS, 'built', 'paved'), null)
})

test('budgetMatched requires equal counts on every arm', () => {
  const arm = (trees: number, reflective_cells: number): ComparisonArm => ({
    temp_delta_c_low: -1,
    temp_delta_c_high: -0.5,
    cost_inr_low: null,
    cost_inr_high: null,
    unpriced_interventions: ['reflective_pavement'],
    trees,
    reflective_cells,
  })
  const matched: Comparison = { random: arm(20, 150), greedy: arm(20, 150), design_guideline: arm(20, 150), ga: arm(20, 150) }
  assert.equal(budgetMatched(matched), true)
  assert.equal(budgetMatched({ ...matched, greedy: arm(19, 150) }), false)
})
