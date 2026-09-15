import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatCoolingPerLakhRange } from '../src/lib/format.ts'
import {
  atCapacity,
  dominantWindow,
  errorRanges,
  formatRankRange,
  rankedKey,
  skippedByReason,
  uncertainRankCount,
} from '../src/lib/ranking.ts'

test('formatRankRange shows a single rank only when it is certain', () => {
  assert.equal(formatRankRange({ rank_best: 4, rank_worst: 4 }), '4')
  assert.equal(formatRankRange({ rank_best: 1, rank_worst: 14 }), '1–14')
  assert.equal(uncertainRankCount([{ rank_best: 1, rank_worst: 1 }, { rank_best: 1, rank_worst: 3 }, { rank_best: 2, rank_worst: 3 }]), 2)
})
import type { RankedStreet, RankingWindow, SkippedStreet } from '../src/types/contracts.ts'

test('atCapacity when every plantable pit is used', () => {
  assert.equal(atCapacity({ trees: 20, tree_capacity: 50 }), false)
  assert.equal(atCapacity({ trees: 11, tree_capacity: 11 }), true)
})

test('skippedByReason groups and puts the largest group first', () => {
  const skip = (osm_name: string, reason: string) => ({ osm_name, window_street_id: 'w', reason }) as SkippedStreet
  const groups = skippedByReason([skip('A', 'no pits'), skip('B', 'outside'), skip('C', 'outside')])
  assert.deepEqual(groups.map((g) => [g.reason, g.streets.length]), [['outside', 2], ['no pits', 1]])
})

test('dominantWindow counts the top streets by window, hand-checked', () => {
  const street = (window_street_id: string) => ({ window_street_id }) as RankedStreet
  // Top 3 of [k, k, f, k]: k holds 2.
  assert.deepEqual(dominantWindow([street('k'), street('k'), street('f'), street('k')], 3), { window_street_id: 'k', streets: 2 })
  assert.equal(dominantWindow([], 10), null)
})

test('formatCoolingPerLakhRange keeps both ends at two decimals', () => {
  // 0.70 °C for ₹74,400 to ₹1,18,040: 0.593 and 0.941 per lakh.
  assert.equal(formatCoolingPerLakhRange(0.593019, 0.94086), '0.59–0.94')
})

test('errorRanges spans the windows, hand-checked', () => {
  const window = (holdout_c: number, mean_c: number) =>
    ({ rmse_holdout_c: holdout_c, rmse_mean_baseline_c: mean_c }) as RankingWindow
  const ranges = errorRanges([window(1.4, 2.03), window(1.16, 1.66), window(1.68, 2.19)])
  assert.deepEqual(ranges, { holdout_c: [1.16, 1.68], mean_baseline_c: [1.66, 2.19] })
})

test('rankedKey separates the same name in different windows', () => {
  assert.notEqual(rankedKey({ window_street_id: 'a', osm_name: 'Laxmi Path' }), rankedKey({ window_street_id: 'b', osm_name: 'Laxmi Path' }))
})
