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

/** True when every arm placed the same number of trees and coated cells, so the comparison is at matched budget. */
export function budgetMatched(comparison: Comparison): boolean {
  const arms: ComparisonArm[] = ARM_ORDER.map((key) => comparison[key])
  return arms.every((arm) => arm.trees === arms[0].trees && arm.reflective_cells === arms[0].reflective_cells)
}
