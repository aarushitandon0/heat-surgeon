"""All API request/response models — the single source of truth (SPEC.md §7).

Frozen after Day 1. Mirrored in frontend/src/types/contracts.ts; a shape change
updates both files in the same commit.

Conventions (SPEC.md §7, CLAUDE.md rule 6):
- Physical quantities carry a unit suffix. Counts, indices and ratios do not.
- Coordinate types carry their unit: BBoxWGS84 is degrees, PointUTM and
  AffineUTM are metres.
- Invalid grid cells are None (null in JSON). There is no separate mask.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import MAX_DESIGN_GRID_CELLS


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Coordinate and grid types -------------------------------------------------

BBoxWGS84 = Annotated[
    tuple[float, float, float, float],
    Field(description="[min_lon, min_lat, max_lon, max_lat] in degrees, EPSG:4326. Display only."),
]
PointUTM = Annotated[
    tuple[float, float],
    Field(description="[easting, northing] in metres, in the enclosing object's crs."),
]
AffineUTM = Annotated[
    tuple[float, float, float, float, float, float],
    Field(description="rasterio affine [cell_size, 0, origin_e, 0, -cell_size, origin_n] in metres."),
]
CellIndex = Annotated[tuple[int, int], Field(description="[row, col]")]
GridShape = Annotated[tuple[int, int], Field(description="[rows, cols]")]
CrsCode = Annotated[str, Field(pattern=r"^EPSG:\d+$")]

SourceAdapter = Literal["earth_engine", "planetary_computer"]
Product = Literal["surface_temperature", "land_cover"]
StreetProfile = Literal["dense_commercial", "leafy_residential", "wide_arterial", "mixed"]
DimensionSource = Literal["osm_tag", "estimated_from_area", "default_assumption"]
CrossSectionSource = Literal["osm_tag", "published_design", "measured_from_imagery", "default_assumption"]
CrossSectionBandKind = Literal[
    "carriageway", "median", "bus_stop", "buffer", "cycle_track", "tree_pit", "footway", "private_property",
]
SurfaceClassName = Literal["canopy", "built", "paved", "bare"]
InterventionType = Literal["tree", "reflective_pavement", "permeable_pavement", "shade_structure"]


def _check_grid(grid: list[list[float | None]], shape: tuple[int, int], name: str) -> None:
    rows, cols = shape
    if len(grid) != rows or any(len(row) != cols for row in grid):
        raise ValueError(f"{name} does not match shape {list(shape)}")


def _check_cost_range(low: float | None, high: float | None) -> None:
    if (low is None) != (high is None):
        raise ValueError("cost_inr_low and cost_inr_high must both be null or both be set")
    if low is not None and low > high:
        raise ValueError(f"cost_inr_low {low} exceeds cost_inr_high {high}")


def _check_band(low: float, high: float, name: str) -> None:
    if low > high:
        raise ValueError(f"{name}_low {low} exceeds {name}_high {high}")


# --- Provenance ----------------------------------------------------------------

class Provenance(Contract):
    """Where a composite came from. Replaces any single capture date or scene ID."""

    product: Product
    date_range: tuple[date, date]
    months: list[Annotated[int, Field(ge=1, le=12)]]
    scene_count: int = Field(ge=0)
    capture_dates: list[date]
    scene_ids: list[str]
    collections: list[str]
    platforms: list[str]
    compositing: str
    cloud_masking: str
    overpass_local_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    native_resolution_m: float = Field(gt=0)
    delivered_resolution_m: float = Field(gt=0)
    source_adapter: SourceAdapter

    @model_validator(mode="after")
    def _scene_ids_match_count(self):
        if len(self.scene_ids) != self.scene_count:
            raise ValueError("scene_ids length must equal scene_count")
        return self


# --- Streets -------------------------------------------------------------------

class StreetSummary(Contract):
    id: str
    name: str
    city: str
    profile: StreetProfile
    bbox_street: BBoxWGS84
    bbox_street_verified: bool
    bbox_window: BBoxWGS84
    cached: bool


class StreetRef(Contract):
    id: str
    name: str


class Building(Contract):
    id: str
    footprint: list[PointUTM]
    height_m: float = Field(gt=0)
    height_source: DimensionSource
    footprint_source: str = Field(
        description="Dataset the footprint came from, verbatim as Overture names it: 'OpenStreetMap', "
                    "'Microsoft ML Buildings', 'Google Open Buildings', ..."
    )


class Road(Contract):
    centerline: list[PointUTM]
    width_m: float = Field(gt=0)
    width_source: DimensionSource


class Sidewalk(Contract):
    polygon: list[PointUTM]
    width_m: float = Field(gt=0)
    width_source: DimensionSource


class CrossSectionBand(Contract):
    """One strip of the street, as offsets across it from the centreline (negative is left of the bearing)."""

    kind: CrossSectionBandKind
    offset_from_m: float
    offset_to_m: float
    plantable: bool

    @model_validator(mode="after")
    def _ordered(self):
        if self.offset_from_m >= self.offset_to_m:
            raise ValueError("offset_from_m must be less than offset_to_m")
        return self


class CrossSection(Contract):
    """How the street's width is divided. Anything whose source is not osm_tag is an assumption, labelled in the UI."""

    source: CrossSectionSource
    reference: str = Field(description="What the source is, e.g. 'PMC Urban Street Design Guidelines 2016, template 18A'.")
    right_of_way_m: float = Field(gt=0)
    right_of_way_source: DimensionSource | Literal["building_footprints"]
    bands: list[CrossSectionBand] = Field(min_length=1)


class StreetGeometry(Contract):
    street_id: str
    crs: CrsCode
    bbox_street: BBoxWGS84
    buildings: list[Building]
    road: Road
    sidewalks: list[Sidewalk]
    cross_section: CrossSection


# --- Thermal grid --------------------------------------------------------------

class ThermalStats(Contract):
    min_c: float
    max_c: float
    mean_c: float
    valid_pixels: int = Field(ge=0)


class ThermalGrid(Contract):
    """Measured land surface temperature on Landsat's native grid, unresampled."""

    street_id: str
    scope: Literal["street", "window"]
    crs: CrsCode
    transform: AffineUTM
    shape: GridShape
    cell_size_m: float = Field(gt=0)
    bbox_wgs84: BBoxWGS84
    lst_c: list[list[float | None]]
    stats: ThermalStats
    provenance: Provenance

    @model_validator(mode="after")
    def _grid_consistent(self):
        _check_grid(self.lst_c, self.shape, "lst_c")
        a, b, _, d, e, _ = self.transform
        if (a, b, d, e) != (self.cell_size_m, 0.0, 0.0, -self.cell_size_m):
            raise ValueError("transform must be north-up with cell_size_m pixels")
        valid = sum(v is not None for row in self.lst_c for v in row)
        if valid != self.stats.valid_pixels:
            raise ValueError(f"stats.valid_pixels {self.stats.valid_pixels} != non-null cells {valid}")
        return self


# --- Calibration ---------------------------------------------------------------

class CalibrationRequest(Contract):
    holdout_fraction: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42


class SurfaceContrast(Contract):
    """Modelled surface temperature of a cell fully of class_a minus one fully of class_b, with its standard error.

    Invariant to which class the fit uses as reference. The standard error assumes independent residuals,
    so it is a diagnostic, not a confidence interval.
    """

    class_a: SurfaceClassName
    class_b: SurfaceClassName
    difference_c: float
    standard_error_c: float = Field(ge=0)


class CalibrationResult(Contract):
    """Baseline surface temperature model fitted on calibration cells (90 m blocks), plus the
    published albedo coefficient range used for albedo interventions, which is not fitted.

    The k fields are differences from paved surface whatever reference class the fit used; the
    parameterisation does not change predictions. contrasts lists every pair with standard errors."""

    street_id: str
    bbox_window: BBoxWGS84
    calibration_resolution_m: float = Field(gt=0)
    t_base_c: float = Field(description="Modelled surface temperature of a fully paved cell.")
    k_canopy_c_per_fraction: float
    k_built_c_per_fraction: float
    k_bare_c_per_fraction: float
    k_albedo_low_c_per_unit_albedo: float = Field(ge=0, description="Published measurement, not fitted.")
    k_albedo_high_c_per_unit_albedo: float = Field(ge=0, description="Published measurement, not fitted.")
    rmse_holdout_c: float = Field(ge=0)
    rmse_mean_baseline_c: float = Field(ge=0)
    r2_holdout: float
    n_cells_fit: int = Field(gt=0)
    n_cells_holdout: int = Field(gt=0)
    fit_reference_class: SurfaceClassName
    contrasts: list[SurfaceContrast] = Field(min_length=1)
    building_footprint_sources: list[str] = Field(min_length=1)
    provenance: list[Provenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _albedo_band(self):
        _check_band(self.k_albedo_low_c_per_unit_albedo, self.k_albedo_high_c_per_unit_albedo, "k_albedo")
        return self


# --- Optimization --------------------------------------------------------------

class OptimizeRequest(Contract):
    """Budget by count, and optionally by rupees. A rupee budget needs every allowed intervention priced:
    with no sourced coating rate, budget_inr_max requires reflective_cells_max = 0."""

    trees_max: int = Field(ge=0)
    reflective_cells_max: int = Field(ge=0)
    budget_inr_max: float | None = Field(default=None, gt=0)
    generations: int = Field(gt=0)
    population: int = Field(gt=0)
    cost_weight_c_per_inr: float = Field(ge=0)
    run_baselines: bool = True
    seed: int = 42


class OptimizeJobHandle(Contract):
    job_id: str
    ws_url: str
    grid_shape: GridShape
    cells: int = Field(gt=0)
    states_per_cell: int = Field(gt=0)


class Intervention(Contract):
    type: InterventionType
    cells: list[CellIndex] = Field(min_length=1)


class OptimizeProgress(Contract):
    type: Literal["progress"]
    job_id: str
    generation: int = Field(ge=0)
    generations_total: int = Field(gt=0)
    best_fitness_score: float = Field(
        description="Dimensionless scalarized objective (SPEC.md §6.3). Not a physical quantity; never displayed as one."
    )
    best_temp_delta_c_low: float
    best_temp_delta_c_high: float
    best_cost_inr_low: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    best_cost_inr_high: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    layout_preview: list[Intervention] | None = Field(
        description="Sent only when the best individual improves; null otherwise."
    )

    @model_validator(mode="after")
    def _ranges(self):
        _check_cost_range(self.best_cost_inr_low, self.best_cost_inr_high)
        _check_band(self.best_temp_delta_c_low, self.best_temp_delta_c_high, "best_temp_delta_c")
        return self


class OptimizeDone(Contract):
    type: Literal["done"]
    job_id: str
    result_url: str


class OptimizeError(Contract):
    type: Literal["error"]
    job_id: str
    code: str
    message: str


OptimizeMessage = Annotated[OptimizeProgress | OptimizeDone | OptimizeError, Field(discriminator="type")]


class ModelError(Contract):
    rmse_holdout_c: float = Field(ge=0)
    rmse_mean_baseline_c: float = Field(ge=0)


class ComparisonArm(Contract):
    """One arm of the matched-budget comparison. Counts are carried so the match is checkable
    even when costs are null."""

    temp_delta_c_low: float
    temp_delta_c_high: float
    cost_inr_low: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    cost_inr_high: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    unpriced_interventions: list[InterventionType]
    trees: int = Field(ge=0)
    reflective_cells: int = Field(ge=0)

    @model_validator(mode="after")
    def _ranges(self):
        _check_cost_range(self.cost_inr_low, self.cost_inr_high)
        _check_band(self.temp_delta_c_low, self.temp_delta_c_high, "temp_delta_c")
        if (self.cost_inr_low is None) != bool(self.unpriced_interventions):
            raise ValueError("cost is null exactly when some intervention is unpriced")
        return self


class Comparison(Contract):
    """random is the mean-seed random layout; design_guideline is good practice with no optimisation."""

    random: ComparisonArm
    greedy: ComparisonArm
    design_guideline: ComparisonArm
    ga: ComparisonArm


class DesignGrid(Contract):
    """Street-aligned 2 m grid. Origin is the outer corner of cell [0, 0]; rows advance
    along bearing_deg (clockwise from UTM grid north), columns to the right of it."""

    crs: CrsCode
    origin_e_m: float
    origin_n_m: float
    bearing_deg: float = Field(ge=0, lt=360)
    cell_size_m: float = Field(gt=0)
    shape: GridShape

    @model_validator(mode="after")
    def _within_cap(self):
        rows, cols = self.shape
        if rows <= 0 or cols <= 0:
            raise ValueError("design grid shape must be positive")
        if rows * cols > MAX_DESIGN_GRID_CELLS:
            raise ValueError(
                f"design grid {rows}x{cols} = {rows * cols} cells exceeds the {MAX_DESIGN_GRID_CELLS}-cell cap"
            )
        return self


class Resolution(Contract):
    measurement_resolution_m: float = Field(gt=0)
    calibration_resolution_m: float = Field(gt=0)
    design_resolution_m: float = Field(gt=0)
    output_kind: Literal["model_output_at_design_resolution"]


class OptimizationResult(Contract):
    job_id: str
    street: StreetRef
    baseline_temp_c: float
    optimized_temp_c_low: float
    optimized_temp_c_high: float
    temp_delta_c_low: float = Field(description="More-cooling end of the band from the published albedo coefficient range.")
    temp_delta_c_high: float = Field(description="Less-cooling end. Equal to temp_delta_c_low when no albedo intervention is used.")
    cost_inr_low: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    cost_inr_high: float | None = Field(ge=0, description="Null when the layout uses an unpriced intervention.")
    unpriced_interventions: list[InterventionType]
    model: ModelError
    comparison: Comparison
    interventions: list[Intervention]
    design_grid: DesignGrid
    cross_section: CrossSection
    plantable_mask: list[list[bool]] = Field(description="Design cells where a tree may be planted, from the cross-section.")
    before_lst_c: list[list[float | None]]
    after_lst_c_low: list[list[float | None]]
    after_lst_c_high: list[list[float | None]]
    resolution: Resolution
    provenance: list[Provenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self):
        _check_cost_range(self.cost_inr_low, self.cost_inr_high)
        if (self.cost_inr_low is None) != bool(self.unpriced_interventions):
            raise ValueError("cost is null exactly when some intervention is unpriced")
        rows, cols = self.design_grid.shape
        if len(self.plantable_mask) != rows or any(len(row) != cols for row in self.plantable_mask):
            raise ValueError(f"plantable_mask does not match shape {list(self.design_grid.shape)}")
        _check_band(self.temp_delta_c_low, self.temp_delta_c_high, "temp_delta_c")
        _check_band(self.optimized_temp_c_low, self.optimized_temp_c_high, "optimized_temp_c")
        _check_grid(self.before_lst_c, self.design_grid.shape, "before_lst_c")
        _check_grid(self.after_lst_c_low, self.design_grid.shape, "after_lst_c_low")
        _check_grid(self.after_lst_c_high, self.design_grid.shape, "after_lst_c_high")
        rows, cols = self.design_grid.shape
        for intervention in self.interventions:
            for row, col in intervention.cells:
                if not (0 <= row < rows and 0 <= col < cols):
                    raise ValueError(f"intervention cell {[row, col]} outside design grid {[rows, cols]}")
        return self
