"""SurfaceTemperatureSource and LandCoverSource protocols (SPEC.md §4.1), plus the
scaling, masking and compositing both adapters share.

Everything above the data layer talks to these protocols, never to a vendor SDK
(CLAUDE.md rule 3). Adapters return composites on their own native grid; nothing
here resamples a measured value.
"""

import calendar
import math
import statistics
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol

import numpy as np

from app import config
from app.contracts import Provenance
from app.data.cache import BBox, DateRange

Affine = tuple[float, float, float, float, float, float]


class SourceError(RuntimeError):
    """A source returned something we refuse to use silently (wrong grid, missing offset, no scenes)."""


# --- What sources return --------------------------------------------------------

@dataclass
class SurfaceTemperatureComposite:
    """Per-pixel median composite on Landsat's native 30 m grid.

    `lst_c` and `albedo` are built from the same masked observations. Pixels with
    fewer than config.MIN_CLEAR_OBSERVATIONS valid observations are NaN in both.
    """

    lst_c: np.ndarray
    albedo: np.ndarray
    clear_count: np.ndarray
    crs: str
    transform: Affine
    provenance: Provenance
    scenes_searched: int


@dataclass
class ReflectanceComposite:
    """Per-pixel median Sentinel-2 L2A surface reflectance (B4 red, B8 NIR) on its native 10 m grid."""

    red: np.ndarray
    nir: np.ndarray
    clear_count: np.ndarray
    crs: str
    transform: Affine
    provenance: Provenance
    scenes_searched: int
    boa_add_offset_applied: bool
    boa_add_offsets_seen: list[float]


class SurfaceTemperatureSource(Protocol):
    source_adapter: str

    def surface_temperature(self, bbox: BBox, date_range: DateRange) -> SurfaceTemperatureComposite:
        """`bbox` must lie exactly on the Landsat 30 m grid; adapters raise rather than resample."""
        ...


class LandCoverSource(Protocol):
    source_adapter: str

    def land_cover_reflectance(self, bbox: BBox, date_range: DateRange) -> ReflectanceComposite:
        """Returns the smallest window on the Sentinel-2 10 m grid that covers `bbox`."""
        ...


# --- Grids, seasons, overpass time ------------------------------------------------

def check_on_grid(bounds: tuple[float, float, float, float], cell_size_m: float, origin_offset_m: float) -> None:
    """Raise unless every edge of `bounds` falls on the grid (origin_offset_m + k * cell_size_m)."""
    for edge in bounds:
        remainder = (edge - origin_offset_m) % cell_size_m
        if not (math.isclose(remainder, 0, abs_tol=1e-6) or math.isclose(remainder, cell_size_m, abs_tol=1e-6)):
            raise SourceError(
                f"window edge {edge} is not on the {cell_size_m} m grid offset by {origin_offset_m} m; "
                "refusing to resample measured values"
            )


def covering_bounds(bounds: tuple[float, float, float, float], cell_size_m: float) -> tuple[float, float, float, float]:
    """Smallest bounds on a zero-offset `cell_size_m` grid that contain `bounds`."""
    min_x, min_y, max_x, max_y = bounds
    return (
        math.floor(min_x / cell_size_m) * cell_size_m,
        math.floor(min_y / cell_size_m) * cell_size_m,
        math.ceil(max_x / cell_size_m) * cell_size_m,
        math.ceil(max_y / cell_size_m) * cell_size_m,
    )


def season_windows(date_range: DateRange) -> list[tuple[date, date]]:
    """One inclusive (first, last) date pair per year, covering date_range.months within date_range."""
    months = sorted(date_range.months)
    if months != list(range(months[0], months[-1] + 1)):
        raise ValueError(f"months must be contiguous, got {months}")
    start, end = date.fromisoformat(date_range.start), date.fromisoformat(date_range.end)
    windows = []
    for year in range(start.year, end.year + 1):
        first = max(date(year, months[0], 1), start)
        last = min(date(year, months[-1], calendar.monthrange(year, months[-1])[1]), end)
        if first <= last:
            windows.append((first, last))
    return windows


def local_overpass_time(acquired: list[datetime]) -> str:
    """Median acquisition clock time, converted to local time with config.LOCAL_UTC_OFFSET_MINUTES, as HH:MM."""
    if not acquired:
        raise SourceError("no acquisitions to take an overpass time from")
    minutes_utc = [dt.astimezone(timezone.utc).hour * 60 + dt.astimezone(timezone.utc).minute for dt in acquired]
    local = round(statistics.median(minutes_utc) + config.LOCAL_UTC_OFFSET_MINUTES) % (24 * 60)
    return f"{local // 60:02d}:{local % 60:02d}"


# --- Landsat Collection 2 Level 2 -----------------------------------------------

def st_b10_to_celsius(raw: np.ndarray) -> np.ndarray:
    """ST_B10 digital numbers to land surface temperature in degrees Celsius. Fill becomes NaN."""
    raw = np.asarray(raw)
    kelvin = raw.astype(np.float64) * config.LANDSAT_ST_B10_SCALE_K_PER_DN + config.LANDSAT_ST_B10_OFFSET_K
    return np.where(raw == config.LANDSAT_FILL_DN, np.nan, kelvin - config.KELVIN_AT_ZERO_CELSIUS)


def st_qa_to_kelvin(raw: np.ndarray) -> np.ndarray:
    """ST_QA digital numbers to surface temperature uncertainty in kelvin. No-data becomes NaN."""
    raw = np.asarray(raw)
    uncertainty_k = raw.astype(np.float64) * config.LANDSAT_ST_QA_SCALE_K_PER_DN
    return np.where(raw == config.LANDSAT_ST_QA_NODATA_DN, np.nan, uncertainty_k)


def sr_to_reflectance(raw: np.ndarray) -> np.ndarray:
    """Surface reflectance digital numbers to unitless reflectance. Fill becomes NaN."""
    raw = np.asarray(raw)
    reflectance = raw.astype(np.float64) * config.LANDSAT_SR_SCALE_PER_DN + config.LANDSAT_SR_OFFSET
    return np.where(raw == config.LANDSAT_FILL_DN, np.nan, reflectance)


def qa_pixel_clear(qa_pixel: np.ndarray) -> np.ndarray:
    """True where no fill, dilated cloud, cirrus, cloud or cloud shadow bit is set."""
    reject_mask = sum(1 << bit for bit in config.LANDSAT_QA_PIXEL_REJECT_BITS)
    return (np.asarray(qa_pixel).astype(np.uint32) & reject_mask) == 0


def liang_broadband_albedo(blue, red, nir, swir1, swir2) -> np.ndarray:
    """Shortwave broadband albedo from Landsat 8/9 OLI surface reflectance (Liang 2001)."""
    c = config.LIANG_2001_OLI_COEFFICIENTS
    return (c["blue"] * blue + c["red"] * red + c["nir"] * nir
            + c["swir1"] * swir1 + c["swir2"] * swir2 + c["intercept"])


def landsat_observation_valid(qa_pixel, st_raw, st_qa_raw, sr_raw_bands) -> np.ndarray:
    """One scene's usable pixels: QA_PIXEL clear, no fill in ST_B10 or any SR band, ST_QA within the cut-off."""
    valid = qa_pixel_clear(qa_pixel) & (np.asarray(st_raw) != config.LANDSAT_FILL_DN)
    for band in sr_raw_bands:
        valid &= np.asarray(band) != config.LANDSAT_FILL_DN
    uncertainty_k = st_qa_to_kelvin(st_qa_raw)
    with np.errstate(invalid="ignore"):
        valid &= uncertainty_k <= config.ST_QA_MAX_UNCERTAINTY_K
    return valid


# --- Sentinel-2 L2A ---------------------------------------------------------------

def s2_reflectance(dn: np.ndarray, boa_add_offset: float, quantification_value: float) -> np.ndarray:
    """L2A digital numbers to surface reflectance: (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE.

    The offset must come from the item's own metadata; it is 0 before processing baseline 04.00.
    """
    dn = np.asarray(dn)
    reflectance = (dn.astype(np.float64) + boa_add_offset) / quantification_value
    return np.where(dn == config.S2_NODATA_DN, np.nan, reflectance)


def scl_clear(scl: np.ndarray) -> np.ndarray:
    """True where the scene classification is not no-data, cloud shadow, cloud or cirrus."""
    return ~np.isin(np.asarray(scl), config.S2_SCL_REJECT_CLASSES)


# --- Compositing ----------------------------------------------------------------

def median_composite(stack: np.ndarray, valid: np.ndarray, min_observations: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel median over axis 0 using only valid observations.

    Returns (median, count). Pixels with fewer than `min_observations` valid observations are NaN.
    """
    masked = np.where(valid, stack, np.nan)
    count = valid.sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels
        median = np.nanmedian(masked, axis=0)
    median[count < min_observations] = np.nan
    return median.astype(np.float32), count.astype(np.uint16)
