// Optimize request defaults and search length presets. No browser globals here, so node tests can import it.

import type { OptimizeRequest } from '../types/contracts.ts'

/** Trees only: a priced layout whose change has only model error attached. Population 120, 400 generations. */
export const DEFAULT_REQUEST: OptimizeRequest = {
  trees_max: 20,
  reflective_cells_max: 0,
  budget_inr_max: null,
  generations: 400,
  population: 120,
  cost_weight_c_per_inr: 0,
  run_baselines: true,
  seed: 42,
}

/**
 * Search length presets. Short keeps the population and cuts generations: on the fixture streets, trees only at
 * 20 trees and seed 42, 150 generations reached the same layout value as 400 in about a third of the time
 * (docs/methodology.md, "Demo safety kit"). The generation total is always on screen, so a short search says so.
 */
export const SEARCH_LENGTHS = {
  full: { generations: 400, population: 120 },
  short: { generations: 150, population: 120 },
} as const satisfies Record<string, Pick<OptimizeRequest, 'generations' | 'population'>>

export type SearchLength = keyof typeof SEARCH_LENGTHS

/** The preset a request matches, or null when generations or population were set by hand. */
export function searchLengthOf(request: OptimizeRequest): SearchLength | null {
  for (const key of Object.keys(SEARCH_LENGTHS) as SearchLength[]) {
    const preset = SEARCH_LENGTHS[key]
    if (request.generations === preset.generations && request.population === preset.population) return key
  }
  return null
}
