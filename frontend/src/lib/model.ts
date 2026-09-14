// Reading calibration and comparison payloads for display.

import type { Comparison, ComparisonArm, SurfaceClassName, SurfaceContrast } from '../types/contracts.ts'

export interface Contrast {
  difference_c: number
  standard_error_c: number
}

/**
 * The contrast of a full cell of `surface` against a full cell of `reference`. The backend lists each pair
 * once in one order; the reverse pair has the opposite sign and the same standard error.
 */
export function contrastAgainst(contrasts: SurfaceContrast[], surface: SurfaceClassName, reference: SurfaceClassName): Contrast | null {
  for (const c of contrasts) {
    if (c.class_a === surface && c.class_b === reference) return { difference_c: c.difference_c, standard_error_c: c.standard_error_c }
    if (c.class_a === reference && c.class_b === surface) return { difference_c: -c.difference_c, standard_error_c: c.standard_error_c }
  }
  return null
}

export const ARM_ORDER = ['random', 'greedy', 'design_guideline', 'ga'] as const satisfies readonly (keyof Comparison)[]

/** [smallest, largest] of a list of counts. */
export function countRange(values: number[]): [number, number] {
  return [Math.min(...values), Math.max(...values)]
}

/**
 * How much more the searched layout cools than a reference layout, in percent of the reference's cooling, at the
 * conservative end (the end the search ranks on). Negative when it cools less. Null when the reference does not cool.
 */
export function coolingMarginPercent(ours: ComparisonArm, reference: ComparisonArm): number | null {
  if (reference.temp_delta_c_high >= 0) return null
  return (ours.temp_delta_c_high / reference.temp_delta_c_high - 1) * 100
}

/** [min, max] padded by `fraction` of the span, and by at least `minPad` either side. */
export function paddedDomain(values: number[], fraction: number, minPad: number): [number, number] {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pad = Math.max((max - min) * fraction, minPad)
  return [min - pad, max + pad]
}

/** True when every arm placed the same number of trees and coated cells, so the comparison is at matched budget. */
export function budgetMatched(comparison: Comparison): boolean {
  const arms: ComparisonArm[] = ARM_ORDER.map((key) => comparison[key])
  return arms.every((arm) => arm.trees === arms[0].trees && arm.reflective_cells === arms[0].reflective_cells)
}
