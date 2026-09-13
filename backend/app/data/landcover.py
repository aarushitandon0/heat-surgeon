"""Sentinel-2 NDVI to canopy, impervious and water fractions on the Landsat 30 m grid (SPEC.md §5.1).

NDVI thresholds live in config.py and are cited in docs/sources.md. Each fraction is
the share of a 30 m cell's observed area whose 10 m NDVI falls in that class, computed
by exact area overlap. No measured value is resampled.
"""

import math
from dataclasses import dataclass

import numpy as np

from app import config


class LandCoverError(RuntimeError):
    """Land cover inputs we refuse to use silently."""


@dataclass
class LandCoverFractions:
    canopy_fraction: np.ndarray
    impervious_fraction: np.ndarray
    water_fraction: np.ndarray
    valid_fraction: np.ndarray


def ndvi(red: np.ndarray, nir: np.ndarray, boa_add_offset_applied: bool) -> np.ndarray:
    """NDVI = (NIR - red) / (NIR + red). Refuses reflectance without a confirmed BOA_ADD_OFFSET."""
    if boa_add_offset_applied is not True:
        raise LandCoverError("Sentinel-2 reflectance has no confirmed BOA_ADD_OFFSET; refusing to compute NDVI")
    with np.errstate(divide="ignore", invalid="ignore"):
        return (nir - red) / (nir + red)


def aggregate_fraction(indicator: np.ndarray, valid: np.ndarray, fine_transform, coarse_transform,
                       coarse_shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Share of each coarse cell's valid area where `indicator` is true, by exact area overlap.

    Both grids must be north-up and share a sub-grid (for 10 m onto Landsat's 30 m grid offset
    by 5 m, a 5 m sub-grid). Returns (fraction, valid_fraction); fraction is NaN where nothing
    in the cell was observed.
    """
    fine_m, coarse_m = fine_transform[0], coarse_transform[0]
    offset_e_m = coarse_transform[2] - fine_transform[2]
    offset_n_m = fine_transform[5] - coarse_transform[5]
    lengths = (fine_m, coarse_m, offset_e_m, offset_n_m)
    if any(v < 0 or not math.isclose(v, round(v), abs_tol=1e-6) for v in lengths):
        raise LandCoverError(f"grids do not share a whole-metre sub-grid: {lengths}")
    sub_m = math.gcd(*(int(round(v)) for v in lengths))
    repeat, block = int(round(fine_m / sub_m)), int(round(coarse_m / sub_m))
    row0, col0 = int(round(offset_n_m / sub_m)), int(round(offset_e_m / sub_m))
    rows, cols = coarse_shape

    def blocks(array: np.ndarray) -> np.ndarray:
        fine = np.repeat(np.repeat(array, repeat, axis=0), repeat, axis=1)
        window = fine[row0:row0 + rows * block, col0:col0 + cols * block]
        if window.shape != (rows * block, cols * block):
            raise LandCoverError("Sentinel-2 window does not cover the Landsat grid")
        return window.reshape(rows, block, cols, block).sum(axis=(1, 3), dtype=np.float64)

    observed = blocks(valid)
    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = blocks(indicator & valid) / observed
    fraction[observed == 0] = np.nan
    return fraction, observed / (block * block)


def land_cover_fractions(red: np.ndarray, nir: np.ndarray, s2_transform, boa_add_offset_applied: bool,
                         landsat_transform, landsat_shape: tuple[int, int]) -> LandCoverFractions:
    values = ndvi(red, nir, boa_add_offset_applied)
    valid = np.isfinite(values)
    classes = {
        "canopy": values >= config.NDVI_FULL_VEGETATION_MIN,
        "water": values < config.NDVI_WATER_MAX,
        "impervious": (values >= config.NDVI_WATER_MAX) & (values < config.NDVI_BARE_SOIL_MAX),
    }
    fractions = {}
    for name, indicator in classes.items():
        fractions[name], valid_fraction = aggregate_fraction(
            indicator & valid, valid, s2_transform, landsat_transform, landsat_shape
        )
    return LandCoverFractions(
        canopy_fraction=fractions["canopy"],
        impervious_fraction=fractions["impervious"],
        water_fraction=fractions["water"],
        valid_fraction=valid_fraction,
    )
