// Reading the street ranking for display. No browser globals, so node tests can import it.

import type { RankedStreet, RankingWindow, SkippedStreet } from '../types/contracts.ts'

/** The list opens on this many streets; the rest are one button away. Drawn heavier on the map. */
export const RANKED_TOP_COUNT = 10

/** Identifies a ranked street: a name can recur in overlapping windows, but is ranked in one. */
export function rankedKey(street: Pick<RankedStreet, 'window_street_id' | 'osm_name'>): string {
  return `${street.window_street_id}/${street.osm_name}`
}

/** [smallest, largest] hold-out error and mean-baseline error across the calibrated windows. */
export function errorRanges(windows: RankingWindow[]): { holdout_c: [number, number]; mean_baseline_c: [number, number] } {
  const holdout = windows.map((w) => w.rmse_holdout_c)
  const mean = windows.map((w) => w.rmse_mean_baseline_c)
  return {
    holdout_c: [Math.min(...holdout), Math.max(...holdout)],
    mean_baseline_c: [Math.min(...mean), Math.max(...mean)],
  }
}

/** "4" when a street's rank is certain within the model's error, "1–14" when it could hold any of those ranks. */
export function formatRankRange(street: Pick<RankedStreet, 'rank_best' | 'rank_worst'>): string {
  return street.rank_best === street.rank_worst ? `${street.rank_best}` : `${street.rank_best}–${street.rank_worst}`
}

/** Streets whose rank is not certain within the model's error. */
export function uncertainRankCount(streets: Pick<RankedStreet, 'rank_best' | 'rank_worst'>[]): number {
  return streets.filter((s) => s.rank_best < s.rank_worst).length
}

/** True when the street's budget is its whole capacity: every plantable pit is used, so the search has little to choose. */
export function atCapacity(street: Pick<RankedStreet, 'trees' | 'tree_capacity'>): boolean {
  return street.trees >= street.tree_capacity
}

/** Skipped streets grouped by reason, largest group first. */
export function skippedByReason(skipped: SkippedStreet[]): { reason: string; streets: SkippedStreet[] }[] {
  const groups = new Map<string, SkippedStreet[]>()
  for (const s of skipped) groups.set(s.reason, [...(groups.get(s.reason) ?? []), s])
  return [...groups].map(([reason, streets]) => ({ reason, streets })).sort((a, b) => b.streets.length - a.streets.length)
}

/** The window holding the most of the top `count` streets, and how many of them it holds. */
export function dominantWindow(streets: RankedStreet[], count: number): { window_street_id: string; streets: number } | null {
  const top = streets.slice(0, count)
  if (top.length === 0) return null
  const counts = new Map<string, number>()
  for (const s of top) counts.set(s.window_street_id, (counts.get(s.window_street_id) ?? 0) + 1)
  const [window_street_id, n] = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]
  return { window_street_id, streets: n }
}
