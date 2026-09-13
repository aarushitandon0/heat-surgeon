"""PlanetaryComputerSource: Landsat C2 L2 and Sentinel-2 L2A via the public Planetary Computer STAC API.

No account needed: assets are signed anonymously through the planetary-computer package.
The only module allowed to import pystac_client or planetary_computer (CLAUDE.md rule 3).

Pixels are read on each product's native grid. A window that does not land exactly on
that grid raises; nothing is resampled.
"""

import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app import config
from app.contracts import Provenance
from app.data.cache import BBox, DateRange
from app.data.sources import (
    ReflectanceComposite,
    SourceError,
    SurfaceTemperatureComposite,
    check_on_grid,
    covering_bounds,
    landsat_observation_valid,
    liang_broadband_albedo,
    local_overpass_time,
    median_composite,
    s2_reflectance,
    scl_clear,
    season_windows,
    sr_to_reflectance,
    st_b10_to_celsius,
)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
LANDSAT_COLLECTION = "landsat-c2-l2"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_SR_ASSETS = ("blue", "red", "nir08", "swir16", "swir22")
READ_WORKERS = 8
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "2"}


def _read_native(href: str, bounds: tuple[float, float, float, float], crs: str, cell_size_m: float) -> np.ndarray:
    """Read `bounds` from one COG band on its own grid. Raises if that would need reprojection or resampling."""
    name = href.split("?")[0].rsplit("/", 1)[-1]
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        if src.crs is None or f"EPSG:{src.crs.to_epsg()}" != crs:
            raise SourceError(f"{name} is in {src.crs}, window is in {crs}; refusing to reproject")
        if not (np.isclose(src.res[0], cell_size_m) and np.isclose(src.res[1], cell_size_m)):
            raise SourceError(f"{name} has {src.res} m pixels, expected {cell_size_m} m")
        window = from_bounds(*bounds, transform=src.transform)
        parts = (window.col_off, window.row_off, window.width, window.height)
        if any(abs(p - round(p)) > 1e-6 for p in parts):
            raise SourceError(f"window {bounds} is not on the native grid of {name}; refusing to resample")
        col, row, width, height = (int(round(p)) for p in parts)
        if col < 0 or row < 0 or col + width > src.width or row + height > src.height:
            raise SourceError(f"window {bounds} extends beyond {name}")
        return src.read(1, window=Window(col, row, width, height))


def _fetch_text(href: str) -> str:
    last_error = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(href, timeout=60) as response:
                return response.read().decode("utf-8")
        except OSError as error:
            last_error = error
    raise SourceError(f"could not fetch {href.split('?')[0]}: {last_error}")


def _boa_offsets(xml: str, processing_baseline: str) -> tuple[dict[str, float], float]:
    """BOA_ADD_OFFSET per physical band and BOA_QUANTIFICATION_VALUE, read from MTD_MSIL2A.xml."""
    quantification = re.search(r"<BOA_QUANTIFICATION_VALUE[^>]*>\s*([\d.]+)\s*<", xml)
    if quantification is None:
        raise SourceError("product metadata has no BOA_QUANTIFICATION_VALUE")
    band_names = dict(re.findall(r'<Spectral_Information bandId="(\d+)" physicalBand="(\w+)"', xml))
    offsets = {
        band_names[band_id]: float(value)
        for band_id, value in re.findall(r'<BOA_ADD_OFFSET band_id="(\d+)">\s*(-?[\d.]+)\s*</BOA_ADD_OFFSET>', xml)
        if band_id in band_names
    }
    baseline = tuple(int(part) for part in processing_baseline.split("."))
    for band in ("B4", "B8"):
        if band not in offsets:
            if baseline >= (4, 0):
                raise SourceError(f"baseline {processing_baseline} product has no BOA_ADD_OFFSET for {band}")
            offsets[band] = 0.0
    return offsets, float(quantification.group(1))


def _check_landsat_scaling(item) -> None:
    """The STAC metadata must agree with the cited ST_B10 scale and offset in config.py."""
    for band in item.assets["lwir11"].extra_fields.get("raster:bands") or []:
        scale, offset = band.get("scale"), band.get("offset")
        if scale is not None and not np.isclose(scale, config.LANDSAT_ST_B10_SCALE_K_PER_DN):
            raise SourceError(f"{item.id} lwir11 scale {scale} disagrees with config")
        if offset is not None and not np.isclose(offset, config.LANDSAT_ST_B10_OFFSET_K):
            raise SourceError(f"{item.id} lwir11 offset {offset} disagrees with config")


class PlanetaryComputerSource:
    source_adapter = "planetary_computer"

    def __init__(self) -> None:
        self._catalog = pystac_client.Client.open(STAC_URL)

    def _search(self, collection: str, bbox: BBox, date_range: DateRange, query: dict) -> list:
        bounds_wgs84 = transform_bounds(bbox.crs, "EPSG:4326", *bbox.bounds)
        items = []
        for first, last in season_windows(date_range):
            search = self._catalog.search(
                collections=[collection],
                bbox=bounds_wgs84,
                datetime=f"{first.isoformat()}/{last.isoformat()}",
                query={"eo:cloud_cover": {"lt": config.SCENE_CLOUD_COVER_MAX_PERCENT}, **query},
            )
            items.extend(search.items())
        return sorted(items, key=lambda item: item.datetime)

    # --- Landsat -----------------------------------------------------------------

    def surface_temperature(self, bbox: BBox, date_range: DateRange) -> SurfaceTemperatureComposite:
        check_on_grid(bbox.bounds, config.LANDSAT_CELL_SIZE_M, config.LANDSAT_GRID_ORIGIN_OFFSET_M)
        searched = self._search(LANDSAT_COLLECTION, bbox, date_range, {
            "platform": {"in": list(config.LANDSAT_PLATFORMS)},
            "landsat:collection_category": {"eq": config.LANDSAT_COLLECTION_CATEGORY},
        })
        items = [item for item in searched if item.properties.get("proj:code") == bbox.crs]
        if not items:
            raise SourceError(f"no Landsat scenes in {bbox.crs} for {date_range}")
        for item in items:
            _check_landsat_scaling(item)

        def read_scene(item) -> dict[str, np.ndarray]:
            signed = planetary_computer.sign(item)
            assets = ("lwir11", "qa", "qa_pixel", *LANDSAT_SR_ASSETS)
            return {a: _read_native(signed.assets[a].href, bbox.bounds, bbox.crs, config.LANDSAT_CELL_SIZE_M)
                    for a in assets}

        with ThreadPoolExecutor(READ_WORKERS) as pool:
            scenes = list(pool.map(read_scene, items))

        valid = np.stack([
            landsat_observation_valid(s["qa_pixel"], s["lwir11"], s["qa"], [s[a] for a in LANDSAT_SR_ASSETS])
            for s in scenes
        ])
        lst_stack = np.stack([st_b10_to_celsius(s["lwir11"]) for s in scenes])
        albedo_stack = np.stack([
            liang_broadband_albedo(*(sr_to_reflectance(s[a]) for a in LANDSAT_SR_ASSETS)) for s in scenes
        ])
        lst_c, clear_count = median_composite(lst_stack, valid, config.MIN_CLEAR_OBSERVATIONS)
        albedo, _ = median_composite(albedo_stack, valid, config.MIN_CLEAR_OBSERVATIONS)

        used = [item for item, scene_valid in zip(items, valid) if scene_valid.any()]
        provenance = Provenance(
            product="surface_temperature",
            date_range=(date.fromisoformat(date_range.start), date.fromisoformat(date_range.end)),
            months=list(date_range.months),
            scene_count=len(used),
            capture_dates=sorted({item.datetime.date() for item in used}),
            scene_ids=[item.id for item in used],
            collections=[LANDSAT_COLLECTION],
            platforms=sorted({item.properties["platform"] for item in used}),
            compositing="per-pixel median",
            cloud_masking=(
                f"scene eo:cloud_cover < {config.SCENE_CLOUD_COVER_MAX_PERCENT}%; "
                "QA_PIXEL fill, dilated cloud, cirrus, cloud and cloud shadow dropped; "
                f"ST_QA uncertainty above {config.ST_QA_MAX_UNCERTAINTY_K} K dropped; "
                f"pixels need at least {config.MIN_CLEAR_OBSERVATIONS} clear observations"
            ),
            overpass_local_time=local_overpass_time([item.datetime for item in used]),
            native_resolution_m=config.LANDSAT_TIRS_NATIVE_RESOLUTION_M,
            delivered_resolution_m=config.LANDSAT_CELL_SIZE_M,
            source_adapter=self.source_adapter,
        )
        min_e, _, _, max_n = bbox.bounds
        cell = config.LANDSAT_CELL_SIZE_M
        return SurfaceTemperatureComposite(
            lst_c=lst_c, albedo=albedo, clear_count=clear_count, crs=bbox.crs,
            transform=(cell, 0.0, min_e, 0.0, -cell, max_n), provenance=provenance,
            scenes_searched=len(searched),
        )

    # --- Sentinel-2 --------------------------------------------------------------

    def land_cover_reflectance(self, bbox: BBox, date_range: DateRange) -> ReflectanceComposite:
        bounds = covering_bounds(bbox.bounds, config.S2_CELL_SIZE_M)
        scl_bounds = covering_bounds(bounds, config.S2_SCL_CELL_SIZE_M)
        searched = self._search(S2_COLLECTION, bbox, date_range, {})

        latest: dict[tuple[str, date], object] = {}
        for item in searched:
            if item.properties.get("proj:code") != bbox.crs:
                continue
            key = (item.properties["s2:mgrs_tile"], item.datetime.date())
            if key not in latest or item.id > latest[key].id:
                latest[key] = item
        items = sorted(latest.values(), key=lambda item: item.datetime)
        if not items:
            raise SourceError(f"no Sentinel-2 scenes in {bbox.crs} for {date_range}")

        rows = round((bounds[3] - bounds[1]) / config.S2_CELL_SIZE_M)
        cols = round((bounds[2] - bounds[0]) / config.S2_CELL_SIZE_M)
        scl_factor = round(config.S2_SCL_CELL_SIZE_M / config.S2_CELL_SIZE_M)
        row_off = round((scl_bounds[3] - bounds[3]) / config.S2_CELL_SIZE_M)
        col_off = round((bounds[0] - scl_bounds[0]) / config.S2_CELL_SIZE_M)

        def read_scene(item) -> dict:
            signed = planetary_computer.sign(item)
            offsets, quantification = _boa_offsets(
                _fetch_text(signed.assets["product-metadata"].href), item.properties["s2:processing_baseline"]
            )
            red_dn = _read_native(signed.assets["B04"].href, bounds, bbox.crs, config.S2_CELL_SIZE_M)
            nir_dn = _read_native(signed.assets["B08"].href, bounds, bbox.crs, config.S2_CELL_SIZE_M)
            scl = _read_native(signed.assets["SCL"].href, scl_bounds, bbox.crs, config.S2_SCL_CELL_SIZE_M)
            # SCL is a class mask, not a measurement: each 20 m class covers its four 10 m pixels exactly.
            scl = np.repeat(np.repeat(scl, scl_factor, axis=0), scl_factor, axis=1)[row_off:row_off + rows,
                                                                                    col_off:col_off + cols]
            return {
                "red": s2_reflectance(red_dn, offsets["B4"], quantification),
                "nir": s2_reflectance(nir_dn, offsets["B8"], quantification),
                "valid": scl_clear(scl) & (red_dn != config.S2_NODATA_DN) & (nir_dn != config.S2_NODATA_DN),
                "offsets": (offsets["B4"], offsets["B8"]),
            }

        with ThreadPoolExecutor(READ_WORKERS) as pool:
            scenes = list(pool.map(read_scene, items))

        valid = np.stack([s["valid"] for s in scenes])
        red, clear_count = median_composite(np.stack([s["red"] for s in scenes]), valid, config.MIN_CLEAR_OBSERVATIONS)
        nir, _ = median_composite(np.stack([s["nir"] for s in scenes]), valid, config.MIN_CLEAR_OBSERVATIONS)

        used = [(item, s) for item, s in zip(items, scenes) if s["valid"].any()]
        provenance = Provenance(
            product="land_cover",
            date_range=(date.fromisoformat(date_range.start), date.fromisoformat(date_range.end)),
            months=list(date_range.months),
            scene_count=len(used),
            capture_dates=sorted({item.datetime.date() for item, _ in used}),
            scene_ids=[item.id for item, _ in used],
            collections=[S2_COLLECTION],
            platforms=sorted({item.properties["platform"] for item, _ in used}),
            compositing="per-pixel median",
            cloud_masking=(
                f"scene eo:cloud_cover < {config.SCENE_CLOUD_COVER_MAX_PERCENT}%; "
                f"SCL classes {', '.join(str(c) for c in config.S2_SCL_REJECT_CLASSES)} dropped; "
                "BOA_ADD_OFFSET read from each product's metadata and applied; "
                f"pixels need at least {config.MIN_CLEAR_OBSERVATIONS} clear observations"
            ),
            overpass_local_time=local_overpass_time([item.datetime for item, _ in used]),
            native_resolution_m=config.S2_CELL_SIZE_M,
            delivered_resolution_m=config.S2_CELL_SIZE_M,
            source_adapter=self.source_adapter,
        )
        cell = config.S2_CELL_SIZE_M
        return ReflectanceComposite(
            red=red, nir=nir, clear_count=clear_count, crs=bbox.crs,
            transform=(cell, 0.0, bounds[0], 0.0, -cell, bounds[3]), provenance=provenance,
            scenes_searched=len(searched), boa_add_offset_applied=True,
            boa_add_offsets_seen=sorted({o for _, s in used for o in s["offsets"]}),
        )
