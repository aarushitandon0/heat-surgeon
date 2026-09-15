import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clampPanelWidth } from '../src/lib/layout.ts'

test('clampPanelWidth keeps the panel between its minimum and the smaller of 720 px and 60% of the window', () => {
  // 1440 px window: 60% is 864, so the cap is 720.
  assert.equal(clampPanelWidth(500, 1440), 500)
  assert.equal(clampPanelWidth(900, 1440), 720)
  assert.equal(clampPanelWidth(100, 1440), 240)
  // 1000 px window: 60% is 600, below 720, so the cap is 600.
  assert.equal(clampPanelWidth(650, 1000), 600)
  // 300 px window: 60% is 180, below the minimum, so the panel stays at 240.
  assert.equal(clampPanelWidth(500, 300), 240)
  // Fractional pointer positions round to whole pixels.
  assert.equal(clampPanelWidth(333.6, 1440), 334)
})
