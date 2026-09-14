import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  formatRecordedDate,
  manifestUrl,
  replayDelaysMs,
  replayForced,
  requestMatches,
  snapshotUrl,
  type StreamEntry,
} from '../src/lib/replay.ts'

test('formatRecordedDate reads the UTC day of an ISO timestamp', () => {
  assert.equal(formatRecordedDate('2026-09-15T05:30:00+00:00'), '15 Sep 2026')
  // 23:30 IST on 1 March is 18:00 UTC the same day.
  assert.equal(formatRecordedDate('2026-03-01T23:30:00+05:30'), '1 Mar 2026')
})
import type { OptimizeRequest } from '../src/types/contracts.ts'

const entry = (elapsed_s: number): StreamEntry => ({ elapsed_s, message: { type: 'done', job_id: 'j', result_url: '/r' } })

test('replayDelaysMs keeps the recorded pace, hand-checked', () => {
  // 0.25 s, 1.5 s and 62.125 s after the start: 250, 1500 and 62125 ms.
  assert.deepEqual(replayDelaysMs([entry(0.25), entry(1.5), entry(62.125)]), [250, 1500, 62125])
  // At twice the pace every delay halves.
  assert.deepEqual(replayDelaysMs([entry(0.25), entry(1.5)], 2), [125, 750])
  // A clock read before the start never schedules into the past.
  assert.deepEqual(replayDelaysMs([entry(-0.1)]), [0])
  assert.throws(() => replayDelaysMs([entry(1)], 0), RangeError)
})

test('snapshot URLs sit under the base URL and escape the street id', () => {
  assert.equal(snapshotUrl('/', 'pune-fc-road', 'stream'), '/snapshot/pune-fc-road/stream.json')
  assert.equal(snapshotUrl('/heat/', 'a b', 'result'), '/heat/snapshot/a%20b/result.json')
  assert.equal(manifestUrl('/'), '/snapshot/manifest.json')
})

test('replayForced by build flag or by ?replay, and not otherwise', () => {
  assert.equal(replayForced('', true), true)
  assert.equal(replayForced('?replay', false), true)
  assert.equal(replayForced('?street=x&replay=1', false), true)
  assert.equal(replayForced('?street=x', false), false)
})

test('requestMatches compares every field', () => {
  const recorded: OptimizeRequest = {
    trees_max: 20,
    reflective_cells_max: 0,
    budget_inr_max: null,
    generations: 400,
    population: 120,
    cost_weight_c_per_inr: 0,
    run_baselines: true,
    seed: 42,
  }
  assert.equal(requestMatches(recorded, { ...recorded }), true)
  assert.equal(requestMatches(recorded, { ...recorded, trees_max: 21 }), false)
  assert.equal(requestMatches(recorded, { ...recorded, budget_inr_max: 100000 }), false)
})
