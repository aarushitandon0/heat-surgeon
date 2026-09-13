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

export interface StreetGeometry {
  street_id: string
  crs: CrsCode
  bbox_street: BBoxWGS84
  buildings: Building[]
  road: Road
  sidewalks: Sidewalk[]
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

/**
 * Baseline surface temperature model fitted on calibration cells (90 m blocks), plus the
 * published albedo coefficient range used for albedo interventions, which is not fitted.
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
  provenance: Provenance[]
}

// --- Optimization -------------------------------------------------------------

export interface OptimizeRequest {
  budget_inr_max: number
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
  best_cost_inr_low: number
  best_cost_inr_high: number
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

export interface ComparisonArm {
  temp_delta_c_low: number
  temp_delta_c_high: number
  cost_inr_low: number
  cost_inr_high: number
}

export interface Comparison {
  random: ComparisonArm
  greedy: ComparisonArm
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
  cost_inr_low: number
  cost_inr_high: number
  model: ModelError
  comparison: Comparison
  interventions: Intervention[]
  design_grid: DesignGrid
  /** Model output at design resolution, not a measurement. */
  before_lst_c: (number | null)[][]
  /** Model output at design resolution, not a measurement. */
  after_lst_c_low: (number | null)[][]
  /** Model output at design resolution, not a measurement. */
  after_lst_c_high: (number | null)[][]
  resolution: Resolution
  provenance: Provenance[]
}
