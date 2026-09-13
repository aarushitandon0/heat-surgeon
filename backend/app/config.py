"""Settings and cited constants: USE_LIVE_DATA, cost ranges, albedo values, thresholds.

Every constant here is either cited in docs/sources.md or marked `# ASSUMPTION:`
and logged in docs/methodology.md (CLAUDE.md rule 7).
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "fixtures"
CACHE_DIR = FIXTURES_DIR / "cache"
STREETS_DIR = FIXTURES_DIR / "streets"


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes"}


# Offline by default: the demo path is the fixture path (CLAUDE.md rule 4).
# Set USE_LIVE_DATA=true to let cache misses reach the network.
USE_LIVE_DATA = _env_flag("USE_LIVE_DATA", False)

# Design grid cap. Set by SPEC.md §6.1: a street needing more cells raises rather
# than being coarsened.
MAX_DESIGN_GRID_CELLS = 4000

# --- Satellite adapter ------------------------------------------------------------

# Which SurfaceTemperatureSource / LandCoverSource implementation to use (CLAUDE.md rule 3).
# planetary_computer since Day 1: no Earth Engine project was registered on the build machine.
ACTIVE_SOURCE_ADAPTER = os.environ.get("SOURCE_ADAPTER", "planetary_computer")
EARTH_ENGINE_PROJECT = os.environ.get("EARTH_ENGINE_PROJECT")

# --- Landsat 8/9 Collection 2 Level 2 (docs/sources.md, Landsat) --------------------

LANDSAT_ST_B10_SCALE_K_PER_DN = 0.00341802
LANDSAT_ST_B10_OFFSET_K = 149.0
LANDSAT_ST_QA_SCALE_K_PER_DN = 0.01
LANDSAT_ST_QA_NODATA_DN = -9999
LANDSAT_SR_SCALE_PER_DN = 0.0000275
LANDSAT_SR_OFFSET = -0.2
LANDSAT_FILL_DN = 0
LANDSAT_QA_PIXEL_REJECT_BITS = (0, 1, 2, 3, 4)  # fill, dilated cloud, cirrus, cloud, cloud shadow
LANDSAT_CELL_SIZE_M = 30.0
LANDSAT_TIRS_NATIVE_RESOLUTION_M = 100.0
LANDSAT_PLATFORMS = ("landsat-8", "landsat-9")
LANDSAT_COLLECTION_CATEGORY = "T1"

# ASSUMPTION: Landsat C2 UTM pixel edges sit at 15 m plus a multiple of 30 m. Observed in
# item proj:transform on 2026-09-14; adapters re-check every read and raise on disagreement.
LANDSAT_GRID_ORIGIN_OFFSET_M = 15.0

KELVIN_AT_ZERO_CELSIUS = 273.15

# Liang (2001) shortwave broadband albedo, applied to OLI surface reflectance bands 2, 4, 5, 6, 7.
LIANG_2001_OLI_COEFFICIENTS = {
    "blue": 0.356, "red": 0.130, "nir": 0.373, "swir1": 0.085, "swir2": 0.072, "intercept": -0.0018,
}

# --- Sentinel-2 L2A (docs/sources.md, Sentinel-2) ----------------------------------------

S2_CELL_SIZE_M = 10.0
S2_SCL_CELL_SIZE_M = 20.0
S2_NODATA_DN = 0
S2_SCL_REJECT_CLASSES = (0, 3, 8, 9, 10)  # no data, cloud shadow, cloud medium, cloud high, cirrus
S2_HARMONIZED_QUANTIFICATION_VALUE = 10000.0  # Earth Engine S2_SR_HARMONIZED only

# --- Masking and compositing thresholds ----------------------------------------------

# ASSUMPTION: scene-level cloud cover pre-filter, percent. Cheap pre-filter only; per-pixel
# masking does the real work. See docs/methodology.md.
SCENE_CLOUD_COVER_MAX_PERCENT = 40.0

# ASSUMPTION: drop observations whose ST_QA surface temperature uncertainty exceeds this. See
# docs/methodology.md.
ST_QA_MAX_UNCERTAINTY_K = 5.0

# ASSUMPTION: a composite pixel needs this many clear observations, else it is null. See
# docs/methodology.md.
MIN_CLEAR_OBSERVATIONS = 5

# --- Window and dates ------------------------------------------------------------------

# ASSUMPTION: pre-monsoon months across three seasons (SPEC.md §4.2). See docs/methodology.md.
SEASON_MONTHS = (3, 4, 5)
SEASON_START = "2024-03-01"
SEASON_END = "2026-05-31"

# SPEC.md §4.6 and §5.2: the 2 km calibration window, as 67 Landsat cells (2,010 m square).
WINDOW_CELLS = 67

# Indian Standard Time, UTC+05:30, no daylight saving. Used only to state overpass clock time.
LOCAL_UTC_OFFSET_MINUTES = 330

# --- OpenStreetMap ------------------------------------------------------------------------

# The Overpass snapshot date used in OSM cache keys. Overpass serves current data, so the key
# names the day it was pulled; the exact database timestamp is stored with the cached result.
OSM_SNAPSHOT_DATE = "2026-09-14"

# --- Surface cover and calibration cells (docs/methodology.md) ---------------------------

# Rasterisation resolution for exact area shares. Not a physical constant: it only needs to nest
# every input grid (10 m Sentinel-2, 30 m Landsat, 2 m design cells).
SURFACE_SUBGRID_M = 1.0

# Calibration cells are 3 x 3 Landsat cells (90 m), close to the 100 m native thermal resolution.
CALIBRATION_BLOCK_CELLS = 3

FOOTWAY_HIGHWAYS = ("footway", "pedestrian", "cycleway", "path", "steps")

# ASSUMPTION: carriageway lane width when OSM gives lanes but no width. See docs/methodology.md.
LANE_WIDTH_M = 3.5

# ASSUMPTION: carriageway width by highway class when OSM gives neither width nor lanes.
DEFAULT_CARRIAGEWAY_WIDTH_M = {
    "trunk": 14.0, "primary": 14.0, "secondary": 10.5, "tertiary": 7.0, "unclassified": 6.0,
    "residential": 6.0, "living_street": 5.0, "service": 4.0,
    "trunk_link": 7.0, "primary_link": 7.0, "secondary_link": 7.0, "tertiary_link": 7.0,
}

# ASSUMPTION: an OSM sidewalk with no width tag takes the IRC:103 minimum walkway for commercial areas.
SIDEWALK_WIDTH_M = 2.5

# ASSUMPTION: any other footway with no width tag takes the IRC:103 minimum clear pathway.
FOOTWAY_WIDTH_M = 1.8

# Albedo escalation test (project decision, Day 3). Within calibration cells at least this
# built, if albedo still correlates with surface temperature above the escalation threshold,
# OSM footprints are too sparse here and Sentinel-2 B11 (NDBI/BSI) is needed.
BUILT_DOMINANT_FRACTION = 0.5
ALBEDO_BUILT_CORRELATION_ESCALATION = 0.2

# --- Albedo effect on surface temperature: published field measurement, not fitted ---------

# Ko et al. (2022): raising pavement albedo from 0.08 to 0.26 cut surface temperature by 0.9 C at
# 09:00 and by 5 C at 15:00, stated as 2.7 C per 0.1 albedo. Our 10:57 overpass lies between.
K_ALBEDO_LOW_C_PER_UNIT_ALBEDO = 5.0     # 0.9 C / 0.18 albedo, 09:00
K_ALBEDO_HIGH_C_PER_UNIT_ALBEDO = 27.0   # 2.7 C per 0.1 albedo, 15:00 peak

# --- Street design grid (docs/sources.md, Street design; docs/methodology.md) -------------

# SPEC.md §6.1: 2 m design cells.
DESIGN_CELL_SIZE_M = 2.0

# ASSUMPTION: a 200 m segment centred on the street's longest straight OSM way, 40 m across
# (20 m either side of the centreline, reaching the building line on FC Road). 100 x 20 = 2,000 cells.
DESIGN_SEGMENT_LENGTH_M = 200.0
DESIGN_CORRIDOR_WIDTH_M = 40.0

# IRC:SP:21-2009 §11.14.1: shade trees planted 8-12 m apart. The minimum is used.
TREE_MIN_SPACING_M = 8.0

# ASSUMPTION: mature crown diameter equal to the minimum spacing, so neighbouring crowns just meet.
TREE_CROWN_DIAMETER_M = 8.0

# IRC:103-2012: 2.5 m minimum walkway for commercial areas (Table 2) plus a 1.8 m minimum
# multi-functional zone for tree planting (6.10). A narrower sidewalk cannot take a tree.
MIN_SIDEWALK_WIDTH_FOR_TREES_M = 4.3

# --- Land cover from NDVI (docs/sources.md, Land cover) ---------------------------------

# Sobrino et al. (2004) NDVI thresholds: below 0.2 bare soil, 0.5 and above full vegetation.
NDVI_BARE_SOIL_MAX = 0.2
NDVI_FULL_VEGETATION_MIN = 0.5

# ASSUMPTION: NDVI below 0 is treated as water. See docs/methodology.md.
NDVI_WATER_MAX = 0.0

# ASSUMPTION: cells more than a quarter water by area are left out of calibration. See docs/methodology.md.
WATER_FRACTION_MAX_FOR_FIT = 0.25

# --- Surface albedo by material (docs/sources.md, Material albedo) -----------------------

# (low, high) broadband albedo, dimensionless. Used when an intervention replaces a surface;
# calibration uses measured Landsat albedo instead.
ALBEDO_BY_MATERIAL = {
    "asphalt_new": (0.05, 0.05),
    "asphalt_aged": (0.10, 0.20),
    "concrete_new": (0.30, 0.50),
    "concrete_aged": (0.20, 0.35),
    "high_albedo_coating": (0.50, 0.50),
    "permeable_concrete_dry": (0.20, 0.35),
    "permeable_concrete_wet": (0.15, 0.15),
}
