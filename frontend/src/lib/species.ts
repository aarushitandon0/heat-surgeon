// Street tree species: a cited reference lookup, never a model input. Nothing here changes a temperature, cost or
// rank. The model is species-agnostic: every tree is an 8 m crown (TREE_CROWN_DIAMETER_M in backend/app/config.py).
// Sources: docs/sources.md [D1] IRC:SP:21-2009 and [D3] PMC Urban Street Design Guidelines 2016.
// No browser globals, so node tests can import it.

import type { CrossSectionBand } from '../types/contracts.ts'

/** Width of the narrowest tree pit band in a cross-section, in metres; null when it has no tree pit band. */
export function narrowestTreePit_m(bands: CrossSectionBand[]): number | null {
  const widths_m = bands.filter((b) => b.kind === 'tree_pit').map((b) => b.offset_to_m - b.offset_from_m)
  return widths_m.length > 0 ? Math.min(...widths_m) : null
}

/** USDG 2016 §5.2 on tree form by street, quoted. It names no street widths, so it is shown, not used to filter. */
export const USDG_FORM_GUIDANCE = [
  'Trees with columnar form are appropriate for narrower planting spaces such as small streets, alleys, and narrow medians.',
  'Trees with overarching canopies and medium density foliage are appropriate on wider streets, such as mixed use streets, throughways, and boulevards.',
  'Medium-sized trees with light to medium density foliage are appropriate on neighborhood residential and commercial streets.',
]

/** The model's crown diameter, for the comparison shown beside each species. Mirrors TREE_CROWN_DIAMETER_M. */
export const MODEL_CROWN_DIAMETER_M = 8

export type SourcedSize = 'large' | 'small' | null

export interface SpeciesEntry {
  botanical_name: string
  /** As printed in the source, where legible. */
  common_name: string | null
  /** Size class as IRC:SP:21-2009 Appendix I describes it; null where the source does not state it legibly. */
  size: SourcedSize
  /** The Appendix I words the size comes from, quoted; null with size. */
  size_quote: string | null
}

export const SPECIES_SOURCE =
  'Indian Roads Congress, IRC:SP:21-2009, Annex E: trees suitable for the Deccan Plateau (which includes Maharashtra); sizes from its Appendix I.'

/**
 * IRC:SP:21-2009 Annex E, trees for the Deccan Plateau, in the source's order. Botanical names are given in their
 * standard spelling where the scanned source misprints them. Palms (a group, not a species) and Polyalthia longifolia
 * (see EXCLUDED_SPECIES) are left out.
 */
export const DECCAN_SPECIES: SpeciesEntry[] = [
  { botanical_name: 'Albizia procera', common_name: 'Safed siris', size: 'large', size_quote: 'Large sizes, handsome, quick growing' },
  { botanical_name: 'Albizia amara', common_name: null, size: null, size_quote: null },
  { botanical_name: 'Amherstia nobilis', common_name: null, size: null, size_quote: null },
  { botanical_name: 'Bischofia javanica', common_name: null, size: null, size_quote: null },
  { botanical_name: 'Colvillea racemosa', common_name: 'Kilbili', size: 'large', size_quote: 'Large sized, handsome, light foliage, flowering' },
  { botanical_name: 'Dalbergia latifolia', common_name: 'Black shisham, rosewood', size: null, size_quote: null },
  { botanical_name: 'Delonix regia', common_name: 'Gulmohar', size: null, size_quote: null },
  { botanical_name: 'Mangifera indica', common_name: 'Desi mango', size: 'large', size_quote: 'Large sized, shade; a dense round crown' },
  { botanical_name: 'Michelia champaca', common_name: 'Swarn champa', size: 'small', size_quote: 'Small sized, flowering; good for isolated plantings' },
  { botanical_name: 'Peltophorum ferrugineum', common_name: 'Yellow gulmohar', size: null, size_quote: null },
  { botanical_name: 'Saraca indica', common_name: 'Sita ashok', size: 'small', size_quote: 'Small sized, handsome, thick foliage, flowering' },
  { botanical_name: 'Santalum album', common_name: 'White sandal', size: null, size_quote: null },
  { botanical_name: 'Tamarindus indica', common_name: 'Imli', size: null, size_quote: null },
]

/** On the Annex E list but not shown, with the reason. */
export const EXCLUDED_SPECIES: { botanical_name: string; reason: string }[] = [
  {
    botanical_name: 'Polyalthia longifolia (Ashok, mast tree)',
    reason: 'Pune’s Urban Street Design Guidelines (2016) §5.2 list Mast Tree (False Ashoka) among trees to avoid, with Eucalyptus, Australian Acacia, Lantana and Leucaena.',
  },
]

/**
 * USDG 2016 §5.2 table "Diameter of Tree Trunk / Min size of tree grate (M)", read from the PDF on 2026-09-15:
 * the smallest square grate each trunk size needs, in metres.
 */
export const USDG_GRATE_BY_TRUNK: { trunk_diameter_max_m: number; grate_side_m: number }[] = [
  { trunk_diameter_max_m: 0.15, grate_side_m: 0.6 },
  { trunk_diameter_max_m: 0.3, grate_side_m: 0.75 },
  { trunk_diameter_max_m: 0.9, grate_side_m: 1.5 },
  { trunk_diameter_max_m: 1.2, grate_side_m: 2 },
]

/**
 * The largest trunk diameter a tree pit band of this width can take, by the USDG grate table: the biggest row whose
 * grate fits across the pit. Null when even the smallest grate does not fit.
 */
export function largestTrunkForPit(pit_width_m: number): { trunk_diameter_max_m: number; grate_side_m: number } | null {
  const fitting = USDG_GRATE_BY_TRUNK.filter((row) => row.grate_side_m <= pit_width_m + 1e-9)
  return fitting.length > 0 ? fitting[fitting.length - 1] : null
}

export type CrownCheck = 'likely_smaller' | 'consistent_unconfirmed' | 'not_checkable'

/**
 * How a species compares with the model's 8 m crown, from the source's size words alone. No source gives a crown
 * diameter, so this can flag a small tree as likely to cool less than modelled, but never confirm a match.
 */
export function crownCheck(size: SourcedSize): CrownCheck {
  if (size === 'small') return 'likely_smaller'
  if (size === 'large') return 'consistent_unconfirmed'
  return 'not_checkable'
}

export const CROWN_CHECK_TEXT: Record<CrownCheck, string> = {
  likely_smaller: `Described as small sized: its crown is likely well under the model's ${MODEL_CROWN_DIAMETER_M} m, so it would cool less than modelled.`,
  consistent_unconfirmed: `Described as large sized: consistent with the model's ${MODEL_CROWN_DIAMETER_M} m crown, but the source gives no crown diameter to confirm it.`,
  not_checkable: `Size not legibly stated in the source: it cannot be checked against the model's ${MODEL_CROWN_DIAMETER_M} m crown.`,
}
