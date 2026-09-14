// Mirrors backend/app/contracts.py (SPEC.md §7). Frozen after Day 1; a shape change
// updates both files in the same commit.
//
// Physical quantities carry a unit suffix; counts, indices and ratios do not.
// Coordinate types carry their unit: BBoxWGS84 is degrees, PointUTM and AffineUTM
// are metres. Invalid grid cells are null; there is no separate mask.

// --- Coordinate and grid types ------------------------------------------------

/** [min_lon, min_lat, max_lon, max_lat] in degrees, EPSG:4326. Display only, never geometry. */
export type BBoxWGS84 = [number, number, number, number]
/** [easting, northing] in metres, in the enclosing object's crs. */
export type PointUTM = [number, number]
/** rasterio affine [cell_size, 0, origin_e, 0, -cell_size, origin_n] in metres. */
export type AffineUTM = [number, number, number, number, number, number]
/** [row, col] */
export type CellIndex = [number, number]
/** [rows, cols] */
export type GridShape = [number, number]
/** "EPSG:<code>" */
export type CrsCode = string
/** ISO date, YYYY-MM-DD. */
export type IsoDate = string

export type SourceAdapter = 'earth_engine' | 'planetary_computer'
export type Product = 'surface_temperature' | 'land_cover'
export type StreetProfile = 'dense_commercial' | 'leafy_residential' | 'wide_arterial' | 'mixed'
export type DimensionSource = 'osm_tag' | 'estimated_from_area' | 'default_assumption'
export type CrossSectionSource = 'osm_tag' | 'published_design' | 'measured_from_imagery' | 'default_assumption'
export type CrossSectionBandKind =
  | 'carriageway' | 'median' | 'bus_stop' | 'buffer' | 'cycle_track' | 'tree_pit' | 'footway' | 'private_property'
export type SurfaceClassName = 'canopy' | 'built' | 'paved' | 'bare'
export type InterventionType = 'tree' | 'reflective_pavement' | 'permeable_pavement' | 'shade_structure'

// --- Provenance ---------------------------------------------------------------

/** Where a composite came from. Replaces any single capture date or scene ID. */
export interface Provenance {
  product: Product
  date_range: [IsoDate, IsoDate]
  months: number[]
  scene_count: number
  capture_dates: IsoDate[]
  scene_ids: string[]
  collections: string[]
  platforms: string[]
  compositing: string
  cloud_masking: string
  overpass_local_time: string
  native_resolution_m: number
  delivered_resolution_m: number
  source_adapter: SourceAdapter
}

// --- Streets ------------------------------------------------------------------

export interface StreetSummary {
  id: string
  name: string
  city: string
  profile: StreetProfile
  bbox_street: BBoxWGS84
  bbox_street_verified: boolean
  bbox_window: BBoxWGS84
  cached: boolean
}

export interface StreetRef {
  id: string
  name: string
}

export interface Building {
  id: string
  footprint: PointUTM[]
  height_m: number
  height_source: DimensionSource
  /** Dataset verbatim as Overture names it: 'OpenStreetMap', 'Microsoft ML Buildings', 'Google Open Buildings'. */
  footprint_source: string
}

export interface Road {
  centerline: PointUTM[]
  width_m: number
  width_source: DimensionSource
}

export interface Sidewalk {
  polygon: PointUTM[]
  width_m: number
  width_source: DimensionSource
}

/** One strip of the street, as offsets across it from the centreline (negative is left of the bearing). */
export interface CrossSectionBand {
  kind: CrossSectionBandKind
  offset_from_m: number
  offset_to_m: number
  plantable: boolean
}

/** How the street's width is divided. Anything whose source is not osm_tag is an assumption, labelled in the UI. */
export interface CrossSection {
  source: CrossSectionSource
  reference: string
  right_of_way_m: number
  right_of_way_source: DimensionSource | 'building_footprints'
  bands: CrossSectionBand[]
}

export interface StreetGeometry {
  street_id: string
  crs: CrsCode
  bbox_street: BBoxWGS84
  buildings: Building[]
  road: Road
  sidewalks: Sidewalk[]
  cross_section: CrossSection
}

// --- Basemap (display only) ---------------------------------------------------

export interface BasemapWay {
  /** OSM highway or waterway value verbatim, e.g. 'primary', 'residential', 'river'. */
  kind: string
  name: string | null
  path: PointUTM[]
}

/** A named OSM building or place (shop, bank, school, temple, park), for place labels. Display only. */
export interface BasemapFeature {
  name: string
  /** OSM tag verbatim as key=value, e.g. 'building=university', 'amenity=bank'. */
  kind: string
  origin: 'osm_building' | 'osm_place'
  /** Where the label goes: a point inside a building footprint, or the place's position. */
  anchor: PointUTM
  /** Building footprint area; null for a place. */
  footprint_area_m2: number | null
}

/** Major roads and rivers across the city, so the 2 km window can be shown in its city context. */
export interface CityLocator {
  city: string
  bbox_wgs84: BBoxWGS84
  /** [min_e, min_n, max_e, max_n] of the locator extent, in metres in the basemap's crs. */
  bounds_m: [number, number, number, number]
  ways: BasemapWay[]
}

/**
 * Context geometry for display: every OSM highway and merged building footprint in the 2 km window, and the
 * city locator, simplified for drawing. Never a model input and never a measurement.
 */
export interface StreetBasemap {
  street_id: string
  crs: CrsCode
  /** [min_e, min_n, max_e, max_n] of the 2 km window, in metres in crs. */
  window_bounds_m: [number, number, number, number]
  /** OSM name of the design street's ways, to find them among roads. */
  street_osm_name: string
  roads: BasemapWay[]
  buildings: PointUTM[][]
  features: BasemapFeature[]
  city: CityLocator
  attribution: string
  osm_base: string | null
}

// --- Thermal grid -------------------------------------------------------------

export interface ThermalStats {
  min_c: number
  max_c: number
  mean_c: number
  valid_pixels: number
}

/** Measured land surface temperature on Landsat's native grid, unresampled. */
export interface ThermalGrid {
  street_id: string
  scope: 'street' | 'window'
  crs: CrsCode
  transform: AffineUTM
  shape: GridShape
  cell_size_m: number
  bbox_wgs84: BBoxWGS84
  lst_c: (number | null)[][]
  stats: ThermalStats
  provenance: Provenance
}

// --- Calibration --------------------------------------------------------------

export interface CalibrationRequest {
  holdout_fraction: number
  seed: number
}

/** A full cell of class_a minus one of class_b. Standard error is a diagnostic, not a confidence interval. */
export interface SurfaceContrast {
  class_a: SurfaceClassName
  class_b: SurfaceClassName
  difference_c: number
  standard_error_c: number
}

/**
 * Baseline surface temperature model fitted on calibration cells (90 m blocks), plus the
 * published albedo coefficient range used for albedo interventions, which is not fitted.
 * The k fields are differences from paved surface whatever reference class the fit used.
 */
export interface CalibrationResult {
  street_id: string
  bbox_window: BBoxWGS84
  calibration_resolution_m: number
  /** Modelled surface temperature of a fully paved cell. */
  t_base_c: number
  k_canopy_c_per_fraction: number
  k_built_c_per_fraction: number
  k_bare_c_per_fraction: number
  /** Published measurement, not fitted. */
  k_albedo_low_c_per_unit_albedo: number
  /** Published measurement, not fitted. */
  k_albedo_high_c_per_unit_albedo: number
  rmse_holdout_c: number
  rmse_mean_baseline_c: number
  r2_holdout: number
  n_cells_fit: number
  n_cells_holdout: number
  fit_reference_class: SurfaceClassName
  contrasts: SurfaceContrast[]
  building_footprint_sources: string[]
  provenance: Provenance[]
}

// --- Optimization -------------------------------------------------------------

/** Budget by count, and optionally by rupees (requires reflective_cells_max = 0 while coatings are unpriced). */
export interface OptimizeRequest {
  trees_max: number
  reflective_cells_max: number
  budget_inr_max?: number | null
  generations: number
  population: number
  cost_weight_c_per_inr: number
  run_baselines: boolean
  seed: number
}

export interface OptimizeJobHandle {
  job_id: string
  ws_url: string
  grid_shape: GridShape
  cells: number
  states_per_cell: number
  /** The grid layout previews index into, so they can be placed on the street. */
  design_grid: DesignGrid
}

export interface Intervention {
  type: InterventionType
  cells: CellIndex[]
}

export interface OptimizeProgress {
  type: 'progress'
  job_id: string
  generation: number
  generations_total: number
  /** Dimensionless scalarized objective. Not a physical quantity; never display it as one. */
  best_fitness_score: number
  best_temp_delta_c_low: number
  best_temp_delta_c_high: number
  /** Null when the layout uses an unpriced intervention. */
  best_cost_inr_low: number | null
  best_cost_inr_high: number | null
  /** Sent only when the best individual improves; null otherwise. */
  layout_preview: Intervention[] | null
}

export interface OptimizeDone {
  type: 'done'
  job_id: string
  result_url: string
}

export interface OptimizeError {
  type: 'error'
  job_id: string
  code: string
  message: string
}

export type OptimizeMessage = OptimizeProgress | OptimizeDone | OptimizeError

export interface ModelError {
  rmse_holdout_c: number
  rmse_mean_baseline_c: number
}

/** Counts are carried so the matched budget is checkable even when costs are null. */
export interface ComparisonArm {
  temp_delta_c_low: number
  temp_delta_c_high: number
  /** Null when the layout uses an unpriced intervention. */
  cost_inr_low: number | null
  cost_inr_high: number | null
  unpriced_interventions: InterventionType[]
  trees: number
  reflective_cells: number
}

export interface Comparison {
  random: ComparisonArm
  greedy: ComparisonArm
  design_guideline: ComparisonArm
  ga: ComparisonArm
}

/**
 * Street-aligned 2 m grid, capped at 4,000 cells. Origin is the outer corner of
 * cell [0, 0]; rows advance along bearing_deg (clockwise from UTM grid north),
 * columns to the right of it.
 */
export interface DesignGrid {
  crs: CrsCode
  origin_e_m: number
  origin_n_m: number
  bearing_deg: number
  cell_size_m: number
  shape: GridShape
}

export interface Resolution {
  measurement_resolution_m: number
  calibration_resolution_m: number
  design_resolution_m: number
  output_kind: 'model_output_at_design_resolution'
}

export interface OptimizationResult {
  job_id: string
  street: StreetRef
  baseline_temp_c: number
  optimized_temp_c_low: number
  optimized_temp_c_high: number
  /** More-cooling end of the band from the published albedo coefficient range. */
  temp_delta_c_low: number
  /** Less-cooling end. Equal to temp_delta_c_low when no albedo intervention is used. */
  temp_delta_c_high: number
  /** Null when the layout uses an unpriced intervention; never shown as a guess. */
  cost_inr_low: number | null
  cost_inr_high: number | null
  unpriced_interventions: InterventionType[]
  model: ModelError
  comparison: Comparison
  interventions: Intervention[]
  design_grid: DesignGrid
  cross_section: CrossSection
  /** Design cells where a tree may be planted, from the cross-section. */
  plantable_mask: boolean[][]
  /** Model output at design resolution, not a measurement. */
  before_lst_c: (number | null)[][]
  /** Model output at design resolution, not a measurement. */
  after_lst_c_low: (number | null)[][]
  /** Model output at design resolution, not a measurement. */
  after_lst_c_high: (number | null)[][]
  resolution: Resolution
  provenance: Provenance[]
}
