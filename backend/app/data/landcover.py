"""Surface cover for the heat model: canopy from Sentinel-2 NDVI, built and paved from OSM, bare as the rest.

Classes are assigned on a 1 m sub-grid of the window, in priority order:
  canopy  NDVI at or above the full-vegetation threshold (what the thermal sensor sees from above)
  built   OSM building footprints
  paved   OSM highway ways buffered to tagged or estimated width (carriageway or footway)
  water   NDVI below zero
  bare    everything else, including sparse and dry vegetation

Fractions for any coarser cell are exact area shares of that sub-grid. Thresholds and width
rules live in config.py. No measured value is resampled: 10 m NDVI is replicated onto the
1 m sub-grid, which it tiles exactly.
"""

import math
from dataclasses import dataclass

import numpy as np
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import LineString, Polygon, mapping

from app import config

BARE, CANOPY, BUILT, CARRIAGEWAY, FOOTWAY, WATER = 0, 1, 2, 3, 4, 5
UNOBSERVED = 255


class LandCoverError(RuntimeError):
    """Land cover inputs we refuse to use silently."""


@dataclass
class SurfaceCover:
    canopy_fraction: np.ndarray
    built_fraction: np.ndarray
    paved_fraction: np.ndarray
    bare_fraction: np.ndarray
    water_fraction: np.ndarray
    observed_fraction: np.ndarray


def ndvi(red: np.ndarray, nir: np.ndarray, boa_add_offset_applied: bool) -> np.ndarray:
    """NDVI = (NIR - red) / (NIR + red). Refuses reflectance without a confirmed BOA_ADD_OFFSET."""
    if boa_add_offset_applied is not True:
        raise LandCoverError("Sentinel-2 reflectance has no confirmed BOA_ADD_OFFSET; refusing to compute NDVI")
    with np.errstate(divide="ignore", invalid="ignore"):
        return (nir - red) / (nir + red)


def _parse_metres(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).lower().replace("m", "").strip())
    except ValueError:
        return None


def way_width_m(tags: dict) -> tuple[float, str] | None:
    """(width in metres, "carriageway" | "footway") for a highway way, or None if it is not a paved surface we map.

    Width comes from the OSM `width` tag, else `lanes` x LANE_WIDTH_M for carriageways, else a class default.
    """
    highway = tags.get("highway")
    width = _parse_metres(tags.get("width"))
    if highway in config.FOOTWAY_HIGHWAYS:
        if tags.get("footway") == "crossing":
            return None  # drawn across the carriageway, which is already paved
        default = config.SIDEWALK_WIDTH_M if tags.get("footway") == "sidewalk" else config.FOOTWAY_WIDTH_M
        return (width or default), "footway"
    if highway in config.DEFAULT_CARRIAGEWAY_WIDTH_M:
        if width is None and str(tags.get("lanes", "")).isdigit():
            width = int(tags["lanes"]) * config.LANE_WIDTH_M
        return (width or config.DEFAULT_CARRIAGEWAY_WIDTH_M[highway]), "carriageway"
    return None


def rasterize_osm(osm: dict, transform: Affine, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Boolean (built, carriageway, footway) masks on the given north-up grid."""
    def burn(shapes: list) -> np.ndarray:
        if not shapes:
            return np.zeros(shape, dtype=bool)
        return rasterize(((s, 1) for s in shapes), out_shape=shape, transform=transform, fill=0,
                         dtype="uint8").astype(bool)

    buildings = [mapping(Polygon(ring)) for b in osm["buildings"] for ring in b["rings"]]
    carriageways, footways = [], []
    for way in osm["highways"]:
        width = way_width_m(way["tags"])
        if width is None or len(way["coords"]) < 2:
            continue
        polygon = mapping(LineString(way["coords"]).buffer(width[0] / 2))
        (carriageways if width[1] == "carriageway" else footways).append(polygon)
    return burn(buildings), burn(carriageways), burn(footways)


def ndvi_on_subgrid(values: np.ndarray, s2_transform, sub_transform: Affine, shape: tuple[int, int]) -> np.ndarray:
    """Replicate 10 m NDVI onto a finer grid that it tiles exactly. Raises if the grids do not nest."""
    factor = s2_transform[0] / sub_transform.a
    col = (sub_transform.c - s2_transform[2]) / sub_transform.a
    row = (s2_transform[5] - sub_transform.f) / sub_transform.a
    if any(v < 0 or not math.isclose(v, round(v), abs_tol=1e-6) for v in (factor, col, row)):
        raise LandCoverError(f"Sentinel-2 grid does not nest in the sub-grid (factor {factor}, offset {col}, {row})")
    factor, col, row = int(round(factor)), int(round(col)), int(round(row))
    fine = np.repeat(np.repeat(values, factor, axis=0), factor, axis=1)[row:row + shape[0], col:col + shape[1]]
    if fine.shape != shape:
        raise LandCoverError("Sentinel-2 window does not cover the sub-grid")
    return fine


def classify_surfaces(red, nir, s2_transform, boa_add_offset_applied: bool, osm: dict,
                      bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, Affine]:
    """Surface class codes on a SURFACE_SUBGRID_M grid covering `bounds`."""
    sub_m = config.SURFACE_SUBGRID_M
    min_e, min_n, max_e, max_n = bounds
    shape = (round((max_n - min_n) / sub_m), round((max_e - min_e) / sub_m))
    transform = Affine(sub_m, 0.0, min_e, 0.0, -sub_m, max_n)
    values = ndvi_on_subgrid(ndvi(red, nir, boa_add_offset_applied), s2_transform, transform, shape)
    built, carriageway, footway = rasterize_osm(osm, transform, shape)

    classes = np.full(shape, BARE, dtype=np.uint8)
    with np.errstate(invalid="ignore"):
        classes[values < config.NDVI_WATER_MAX] = WATER
        classes[footway] = FOOTWAY
        classes[carriageway] = CARRIAGEWAY
        classes[built] = BUILT
        classes[values >= config.NDVI_FULL_VEGETATION_MIN] = CANOPY
    classes[~np.isfinite(values)] = UNOBSERVED
    return classes, transform


def _trim_blocks(array: np.ndarray, block: int) -> np.ndarray:
    rows, cols = array.shape[0] // block, array.shape[1] // block
    return array[:rows * block, :cols * block].reshape(rows, block, cols, block)


def block_fractions(classes: np.ndarray, block: int) -> SurfaceCover:
    """Area share of each class in non-overlapping block x block cells (trailing partial blocks dropped)."""
    blocks = _trim_blocks(classes, block)
    observed = (blocks != UNOBSERVED).sum(axis=(1, 3)).astype(np.float64)

    def share(*codes: int) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.isin(blocks, codes).sum(axis=(1, 3)) / observed

    return SurfaceCover(
        canopy_fraction=share(CANOPY),
        built_fraction=share(BUILT),
        paved_fraction=share(CARRIAGEWAY, FOOTWAY),
        bare_fraction=share(BARE),
        water_fraction=share(WATER),
        observed_fraction=observed / (block * block),
    )


def block_mean(values: np.ndarray, block: int) -> np.ndarray:
    """Mean of non-overlapping block x block cells (trailing partial blocks dropped); NaN if any member is NaN."""
    return _trim_blocks(np.asarray(values, dtype=np.float64), block).mean(axis=(1, 3))
