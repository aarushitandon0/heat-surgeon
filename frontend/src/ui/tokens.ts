// Reads design tokens from tokens.css for drawing surfaces (canvas) that cannot use var().
// The thermal ramp is read here for measured and modelled grids only.

import { parseHexColor, type RGB } from '../lib/thermal.ts'

function readToken(name: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!value) throw new Error(`Design token ${name} is not defined in tokens.css`)
  return value
}

const THERMAL_RAMP_TOKENS = ['--t-00', '--t-25', '--t-50', '--t-75', '--t-100'] as const

export function readThermalRamp(): RGB[] {
  return THERMAL_RAMP_TOKENS.map((name) => parseHexColor(readToken(name)))
}

export type SurfaceToken = '--base' | '--panel' | '--rule' | '--paper' | '--paper-dim'

/** Non-data colours for canvas strokes and text. */
export function readSurfaceColor(name: SurfaceToken): string {
  return readToken(name)
}

export function readMonoFont(size_px: number): string {
  return `${size_px}px ${readToken('--font-mono')}`
}
