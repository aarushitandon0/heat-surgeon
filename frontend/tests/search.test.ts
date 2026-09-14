import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEFAULT_REQUEST, SEARCH_LENGTHS, searchLengthOf } from '../src/lib/search.ts'

test('the default request is the full search', () => {
  assert.equal(searchLengthOf(DEFAULT_REQUEST), 'full')
  assert.deepEqual(SEARCH_LENGTHS.full, { generations: 400, population: 120 })
})

test('searchLengthOf names a preset only when both generations and population match', () => {
  assert.equal(searchLengthOf({ ...DEFAULT_REQUEST, ...SEARCH_LENGTHS.short }), 'short')
  // 150 generations with a hand-set population of 80 is neither preset.
  assert.equal(searchLengthOf({ ...DEFAULT_REQUEST, generations: 150, population: 80 }), null)
  assert.equal(searchLengthOf({ ...DEFAULT_REQUEST, generations: 399 }), null)
})
