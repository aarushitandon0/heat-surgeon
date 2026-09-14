"""Street services behind the API: summaries, geometry, thermal grids, calibration, and result assembly.

Everything here reads fixtures through the cache. With USE_LIVE_DATA false (the default) a street that was
never prefetched raises CacheMiss; nothing is fetched or invented.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from rasterio.warp import transform_bounds
from shapely.geometry import LineString, Polygon

from app import config
from app.contracts import (
    BasemapFeature,
    BasemapWay,
    Building,
    CityLocator,
    CalibrationRequest,
    CalibrationResult,
    Comparison,
    ComparisonArm,
    ModelError,
    OptimizationResult,
    OptimizeRequest,
    Resolution,
    Road,
    Sidewalk,
    StreetBasemap,
    StreetGeometry,
    StreetRef,
    StreetSummary,
    ThermalGrid,
    ThermalStats,
)
from app.data.cache import load
from app.data.fixtures import CachedWindow, load_window, street_manifest, window_keys
from app.data.footprints import overture_key
from app.data.osm import city_bbox, load_city_ways, osm_key
from app.model import cost
from app.model.validate import CalibrationRun, calibrate
from app.optimizer.encoding import TREE, Budget, Objectives, StreetGrid, segment_frame, street_grid_for


class UnpricedBudget(ValueError):
    """A rupee budget was requested for interventions that have no sourced cost."""


def street_ids() -> list[str]:
    return sorted(p.stem for p in config.STREETS_DIR.glob("*.json"))


def street_cached(manifest: dict) -> bool:
    landsat_key, s2_key = window_keys(manifest)
    return all(load(key) is not None for key in (landsat_key, s2_key, osm_key(landsat_key.bbox),
                                                  overture_key(landsat_key.bbox)))


def street_summary(street_id: str) -> StreetSummary:
    m = street_manifest(street_id)
    return StreetSummary(id=m["id"], name=m["name"], city=m["city"], profile=m["profile"], bbox_street=m["bbox_street"],
                         bbox_street_verified=m["bbox_street_verified"], bbox_window=m["bbox_window"],
                         cached=street_cached(m))


@dataclass
class StreetContext:
    window: CachedWindow
    run: CalibrationRun
    grid: StreetGrid


@lru_cache(maxsize=8)
def street_context(street_id: str) -> StreetContext:
    """Calibration with the default request and the design grid built on it. Cached per street."""
    window = load_window(street_id)
    run = calibrate(street_id, CalibrationRequest())
    return StreetContext(window=window, run=run, grid=street_grid_for(window, run.model))


@lru_cache(maxsize=32)
def _calibration(street_id: str, holdout_fraction: float, seed: int) -> CalibrationResult:
    return calibrate(street_id, CalibrationRequest(holdout_fraction=holdout_fraction, seed=seed)).result


def calibration(street_id: str, request: CalibrationRequest) -> CalibrationResult:
    return _calibration(street_id, request.holdout_fraction, request.seed)


# --- Geometry ----------------------------------------------------------------------------------

def building_height(tags: dict, footprint_area_m2: float) -> tuple[float, str]:
    """(height_m, height_source) from OSM height, else building:levels, else storeys estimated from footprint
    area (config.BUILDING_STOREYS_BY_FOOTPRINT_AREA_M2), else the default for a degenerate footprint. Zero or
    negative tags (seen in Pune OSM) are treated as missing."""
    try:
        height_m = float(str(tags["height"]).lower().replace("m", "").strip())
        if height_m > 0:
            return height_m, "osm_tag"
    except (KeyError, ValueError):
        pass
    try:
        levels = float(tags["building:levels"])
        if levels > 0:
            return levels * config.STOREY_HEIGHT_M, "osm_tag"
    except (KeyError, ValueError):
        pass
    if footprint_area_m2 > 0:
        storeys = next(n for bound_m2, n in config.BUILDING_STOREYS_BY_FOOTPRINT_AREA_M2 if footprint_area_m2 < bound_m2)
        return storeys * config.STOREY_HEIGHT_M, "estimated_from_area"
    return config.DEFAULT_BUILDING_HEIGHT_M, "default_assumption"


def _band_polygon(frame: dict, offset_from_m: float, offset_to_m: float) -> list[tuple[float, float]]:
    start, along, right = frame["start"], frame["along"], frame["right"]
    length = config.DESIGN_SEGMENT_LENGTH_M
    corners = [start + right * offset_from_m, start + along * length + right * offset_from_m,
               start + along * length + right * offset_to_m, start + right * offset_to_m]
    return [(round(float(p[0]), 2), round(float(p[1]), 2)) for p in corners + corners[:1]]


def street_geometry(street_id: str) -> StreetGeometry:
    ctx = street_context(street_id)
    frame = segment_frame(ctx.window)
    section = ctx.grid.cross_section
    segment = LineString([frame["start"], frame["end"]]).buffer(config.GEOMETRY_BUILDING_RADIUS_M)
    tags_by_id = {b["id"]: b["tags"] for b in ctx.window.osm["buildings"]}
    buildings = []
    for b in ctx.window.buildings:
        ring = b["rings"][0]
        if not Polygon(ring).intersects(segment):
            continue
        height_m, height_source = building_height(tags_by_id.get(b["id"], {}), Polygon(ring).area)
        buildings.append(Building(id=b["id"], footprint=[tuple(p) for p in ring], height_m=height_m,
                                  height_source=height_source, footprint_source=b["footprint_source"]))
    source = "osm_tag" if section.source == "osm_tag" else "default_assumption"
    carriageway = [b for b in section.bands if b.kind == "carriageway"]
    carriageway_m = sum(b.offset_to_m - b.offset_from_m for b in carriageway)
    sidewalks = [Sidewalk(polygon=_band_polygon(frame, b.offset_from_m, b.offset_to_m),
                          width_m=b.offset_to_m - b.offset_from_m, width_source=source)
                 for b in section.bands if b.kind == "footway"]
    m = ctx.window.manifest
    return StreetGeometry(
        street_id=street_id, crs=ctx.window.bbox.crs, bbox_street=m["bbox_street"], buildings=buildings,
        road=Road(centerline=[tuple(map(float, frame["start"])), tuple(map(float, frame["end"]))],
                  width_m=carriageway_m, width_source=source),
        sidewalks=sidewalks, cross_section=section,
    )


# --- Basemap -----------------------------------------------------------------------------------

def _simplified_path(coords: list[list[float]], tolerance_m: float) -> list[tuple[float, float]]:
    line = LineString(coords).simplify(tolerance_m, preserve_topology=False)
    return [(round(x, 1), round(y, 1)) for x, y in line.coords]


def _osm_label(tags: dict) -> str | None:
    return tags.get("name:en") or tags.get("name")


def _named_features(osm_buildings: list[dict]) -> list[BasemapFeature]:
    """The largest named OSM buildings, as label candidates. Lower-case names are mapper notes ('cs department'),
    not place names, so they are skipped; the frontend shows only a few after collision."""
    features = []
    for b in osm_buildings:
        name = _osm_label(b["tags"])
        polygon = Polygon(b["rings"][0])
        if not name or not name[0].isupper() or not polygon.is_valid or polygon.area <= 0:
            continue
        anchor = polygon.representative_point()
        features.append(BasemapFeature(name=name, kind=b["tags"].get("building", "yes"),
                                       anchor=(round(anchor.x, 1), round(anchor.y, 1)),
                                       footprint_area_m2=round(polygon.area, 1)))
    features.sort(key=lambda f: -f.footprint_area_m2)
    return features[:config.BASEMAP_NAMED_FEATURES_MAX]


@lru_cache(maxsize=8)
def street_basemap(street_id: str) -> StreetBasemap:
    """OSM highways and merged footprints for the window, plus the city locator. Display geometry only."""
    window = load_window(street_id)
    crs = window.bbox.crs
    city = window.manifest["city"]
    city_ways = load_city_ways(city, crs, allow_network=False)
    window_m, city_m = config.BASEMAP_WINDOW_SIMPLIFY_M, config.BASEMAP_CITY_SIMPLIFY_M
    roads = [BasemapWay(kind=w["tags"]["highway"], name=_osm_label(w["tags"]), path=_simplified_path(w["coords"], window_m))
             for w in window.osm["highways"] if len(w["coords"]) >= 2]
    buildings = [ring for ring in (_simplified_path(b["rings"][0], window_m) for b in window.buildings) if len(ring) >= 4]
    return StreetBasemap(
        street_id=street_id, crs=crs, window_bounds_m=window.bbox.bounds, street_osm_name=window.manifest["osm_name"],
        roads=roads, buildings=buildings, features=_named_features(window.osm["buildings"]),
        city=CityLocator(city=city, bbox_wgs84=config.CITY_LOCATOR_BOUNDS_WGS84[city], bounds_m=city_bbox(city, crs).bounds,
                         ways=[BasemapWay(kind=w["kind"], name=w["name"], path=_simplified_path(w["coords"], city_m))
                               for w in city_ways["ways"] if len(w["coords"]) >= 2]),
        attribution=f"{window.osm['attribution']}. Footprints also from {window.overture['attribution']}.",
        osm_base=window.osm["osm_base"],
    )


# --- Thermal -----------------------------------------------------------------------------------

def thermal_grid(street_id: str, scope: str) -> ThermalGrid:
    window = load_window(street_id)
    lst = window.landsat.arrays["lst_c"]
    a, _, c, _, e, f = window.landsat.metadata["transform"][:6]
    row0, col0, rows, cols = 0, 0, lst.shape[0], lst.shape[1]
    if scope == "street":
        min_e, min_n, max_e, max_n = transform_bounds("EPSG:4326", window.bbox.crs, *window.manifest["bbox_street"])
        col0 = max(0, math.floor((min_e - c) / a))
        row0 = max(0, math.floor((f - max_n) / -e))
        cols = min(lst.shape[1], math.ceil((max_e - c) / a)) - col0
        rows = min(lst.shape[0], math.ceil((f - min_n) / -e)) - row0
    sub = lst[row0:row0 + rows, col0:col0 + cols]
    valid = sub[np.isfinite(sub)]
    left, top = c + col0 * a, f + row0 * e
    bbox = transform_bounds(window.bbox.crs, "EPSG:4326", left, top + rows * e, left + cols * a, top)
    return ThermalGrid(
        street_id=street_id, scope=scope, crs=window.bbox.crs, transform=(a, 0.0, left, 0.0, e, top),
        shape=(rows, cols), cell_size_m=a, bbox_wgs84=tuple(round(v, 5) for v in bbox),
        lst_c=[[None if not np.isfinite(v) else round(float(v), 2) for v in row] for row in sub],
        stats=ThermalStats(min_c=round(float(valid.min()), 2), max_c=round(float(valid.max()), 2),
                           mean_c=round(float(valid.mean()), 2), valid_pixels=int(valid.size)),
        provenance=window.landsat_provenance,
    )


# --- Optimization ------------------------------------------------------------------------------

def budget_for(request: OptimizeRequest) -> Budget:
    """Count budget, tightened by a rupee budget when one is given (conservative: the high end of the range)."""
    trees = request.trees_max
    if request.budget_inr_max is not None:
        priced = {"tree": request.trees_max, "reflective_pavement": request.reflective_cells_max}
        missing = cost.unpriced(priced)
        if missing:
            raise UnpricedBudget(f"budget_inr_max needs every allowed intervention priced; no sourced rate for "
                                 f"{', '.join(missing)}. Set reflective_cells_max to 0 or omit budget_inr_max.")
        trees = min(trees, math.floor(request.budget_inr_max / cost.unit_cost_inr("tree")[1]))
    return Budget(trees=trees, reflective_cells=request.reflective_cells_max)


def arm(objectives: Objectives) -> ComparisonArm:
    return ComparisonArm(temp_delta_c_low=objectives.temp_delta_c_low, temp_delta_c_high=objectives.temp_delta_c_high,
                         cost_inr_low=objectives.cost_inr_low, cost_inr_high=objectives.cost_inr_high,
                         unpriced_interventions=list(objectives.unpriced_interventions), trees=objectives.trees,
                         reflective_cells=objectives.reflective_cells)


def random_arm(grid: StreetGrid, budget: Budget) -> ComparisonArm:
    """Mean temperature change over RANDOM_BASELINE_SEEDS random layouts; counts and cost from seed 0."""
    from app.optimizer.baselines import random_layout

    runs = [grid.evaluate(random_layout(grid, budget, np.random.default_rng(s))) for s in range(config.RANDOM_BASELINE_SEEDS)]
    first = arm(runs[0])
    return first.model_copy(update={"temp_delta_c_low": float(np.mean([r.temp_delta_c_low for r in runs])),
                                    "temp_delta_c_high": float(np.mean([r.temp_delta_c_high for r in runs]))})


def _grid_values(values: np.ndarray) -> list[list[float | None]]:
    return [[None if not np.isfinite(v) else round(float(v), 3) for v in row] for row in values]


def optimization_result(job_id: str, street_id: str, genome: np.ndarray, comparison: Comparison) -> OptimizationResult:
    ctx = street_context(street_id)
    grid, window = ctx.grid, ctx.window
    objectives = grid.evaluate(genome)
    low, high = grid.cell_deltas(genome)
    before = grid.before_lst_c
    baseline_c = float(np.nanmean(before))
    dg = grid.design_grid
    return OptimizationResult(
        job_id=job_id, street=StreetRef(id=street_id, name=window.manifest["name"]),
        baseline_temp_c=baseline_c,
        optimized_temp_c_low=baseline_c + objectives.temp_delta_c_low,
        optimized_temp_c_high=baseline_c + objectives.temp_delta_c_high,
        temp_delta_c_low=objectives.temp_delta_c_low, temp_delta_c_high=objectives.temp_delta_c_high,
        cost_inr_low=objectives.cost_inr_low, cost_inr_high=objectives.cost_inr_high,
        unpriced_interventions=list(objectives.unpriced_interventions),
        model=ModelError(rmse_holdout_c=ctx.run.result.rmse_holdout_c,
                         rmse_mean_baseline_c=ctx.run.result.rmse_mean_baseline_c),
        comparison=comparison, interventions=grid.to_interventions(genome), design_grid=dg,
        cross_section=grid.cross_section,
        plantable_mask=grid.allowed[..., TREE].tolist(),
        before_lst_c=_grid_values(before), after_lst_c_low=_grid_values(before + low),
        after_lst_c_high=_grid_values(before + high),
        resolution=Resolution(measurement_resolution_m=config.LANDSAT_CELL_SIZE_M,
                              calibration_resolution_m=ctx.run.result.calibration_resolution_m,
                              design_resolution_m=dg.cell_size_m, output_kind="model_output_at_design_resolution"),
        provenance=[window.landsat_provenance, window.sentinel2_provenance],
    )
