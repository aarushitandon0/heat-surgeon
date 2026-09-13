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
