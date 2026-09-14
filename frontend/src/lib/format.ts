// Display formatting. Every number is rounded here and nowhere else, so the precision on
// screen is one decision, recorded in docs/methodology.md ("Frontend display").

import type { CrossSectionSource, InterventionType, StreetProfile } from '../types/contracts.ts'

export const MINUS = '−'
export const EN_DASH = '–'

/** Absolute surface temperatures. */
export const TEMP_DECIMALS = 1
/** Modelled changes. Arms differ by about 0.1 °C, so one decimal would hide the ranking. */
export const DELTA_DECIMALS = 2
/** Model error and coefficients. */
export const ERROR_DECIMALS = 2
/** Cost ends are rounded outward to this many significant figures: an estimate, not a quote. */
export const COST_SIGNIFICANT_FIGURES = 2

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Fixed decimals with a true minus sign. Values that round to zero carry no sign. */
export function formatNumber(value: number, decimals: number): string {
  const fixed = Math.abs(value).toFixed(decimals)
  return (value < 0 && Number(fixed) !== 0 ? MINUS : '') + fixed
}

/** Like formatNumber, with an explicit plus on positive values. */
export function formatSigned(value: number, decimals: number): string {
  const fixed = Math.abs(value).toFixed(decimals)
  if (Number(fixed) === 0) return fixed
  return (value < 0 ? MINUS : '+') + fixed
}

/** A modelled change band, more-cooling end first. Collapses to one value when the ends agree. */
export function formatDeltaBand(low_c: number, high_c: number, decimals = DELTA_DECIMALS): string {
  const low = formatSigned(low_c, decimals)
  const high = formatSigned(high_c, decimals)
  return low === high ? low : `${low} to ${high}`
}

/** Percent margins between layouts. Whole percent: the margins are read against a much larger model error. */
export const PERCENT_DECIMALS = 0

export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value)
}

/** "25" or "25–26". */
export function formatCountRange([min, max]: [number, number]): string {
  return min === max ? formatCount(min) : `${formatCount(min)}${EN_DASH}${formatCount(max)}`
}

/** Round to significant figures, towards floor or ceiling. */
export function roundSignificant(value: number, figures: number, direction: 'floor' | 'ceil'): number {
  if (value === 0) return 0
  const step = 10 ** (Math.floor(Math.log10(Math.abs(value))) - figures + 1)
  // Guard against 118000 / 1000 landing a hair above an integer and ceiling one step too far.
  const scaled = Number((value / step).toPrecision(12))
  return Math[direction](scaled) * step
}

/**
 * A cost range in rupees, ends rounded outward so the range never narrows. Returns null when
 * either end is null (an unpriced intervention). Never produces a midpoint.
 */
export function formatInrRange(low_inr: number | null, high_inr: number | null): string | null {
  if (low_inr === null || high_inr === null) return null
  const low = formatCount(roundSignificant(low_inr, COST_SIGNIFICANT_FIGURES, 'floor'))
  const high = formatCount(roundSignificant(high_inr, COST_SIGNIFICANT_FIGURES, 'ceil'))
  return low === high ? `₹${low}` : `₹${low}${EN_DASH}${high}`
}

/** "Mar–May, 2024–2026" from provenance months and date range. Non-contiguous months are listed. */
export function formatSeasons(months: number[], date_range: [string, string]): string {
  const sorted = [...new Set(months)].sort((a, b) => a - b)
  const contiguous = sorted.every((month, i) => i === 0 || month === sorted[i - 1] + 1)
  const names = sorted.map((month) => MONTH_NAMES[month - 1])
  const monthText = contiguous && names.length > 1 ? `${names[0]}${EN_DASH}${names[names.length - 1]}` : names.join(', ')
  const firstYear = date_range[0].slice(0, 4)
  const lastYear = date_range[1].slice(0, 4)
  const years = firstYear === lastYear ? firstYear : `${firstYear}${EN_DASH}${lastYear}`
  return `${monthText}, ${years}`
}

/**
 * provenance.overpass_local_time is local time at the street. Every street is in Pune, so the zone
 * is IST. A street outside India needs the zone from the backend, not this label.
 */
export const LOCAL_TIME_ZONE_LABEL = 'IST'

export function formatOverpass(local_time: string): string {
  return `${local_time} ${LOCAL_TIME_ZONE_LABEL}`
}

/** An unsigned band, lower end first. Collapses to one value when the ends agree. */
export function formatBand(low: number, high: number, decimals: number): string {
  const a = formatNumber(low, decimals)
  const b = formatNumber(high, decimals)
  return a === b ? a : `${a}${EN_DASH}${b}`
}

export function formatLatitude(lat_deg: number, decimals = 4): string {
  return `${Math.abs(lat_deg).toFixed(decimals)}° ${lat_deg < 0 ? 'S' : 'N'}`
}

export function formatLongitude(lon_deg: number, decimals = 4): string {
  return `${Math.abs(lon_deg).toFixed(decimals)}° ${lon_deg < 0 ? 'W' : 'E'}`
}

/** "FC Road" from "FC Road, Pune": the street's own name, for map labels. */
export function streetShortName(name: string): string {
  return name.split(',')[0].trim()
}

export const SOURCE_ADAPTER_LABELS = {
  planetary_computer: 'Microsoft Planetary Computer',
  earth_engine: 'Google Earth Engine',
} as const

export const SURFACE_LABELS = {
  canopy: 'Canopy',
  built: 'Roof',
  paved: 'Paved',
  bare: 'Bare ground',
} as const

export const PROFILE_LABELS: Record<StreetProfile, string> = {
  dense_commercial: 'Dense commercial',
  leafy_residential: 'Leafy residential',
  wide_arterial: 'Wide arterial',
  mixed: 'Mixed',
}

export const INTERVENTION_LABELS: Record<InterventionType, string> = {
  tree: 'street tree',
  reflective_pavement: 'reflective pavement coating',
  permeable_pavement: 'permeable paving',
  shade_structure: 'shade structure',
}

export const CROSS_SECTION_SOURCE_LABELS: Record<CrossSectionSource, string> = {
  osm_tag: 'From OpenStreetMap tags.',
  published_design: 'Assumed from a published design template, not a survey of the street.',
  measured_from_imagery: 'Measured from imagery.',
  default_assumption: 'Default assumption, not a survey of the street.',
}
