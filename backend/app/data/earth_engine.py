"""EarthEngineSource: Landsat C2 L2 and Sentinel-2 L2A via the Earth Engine Python API.

The only module in the repo allowed to import `ee` (CLAUDE.md rule 3).

NOT YET RUN AGAINST A LIVE ACCOUNT. No Earth Engine project was registered on the
build machine on Day 1, so the active adapter is planetary_computer. Treat this module
as unverified until one real pull through it succeeds and matches the Planetary
Computer composite for the same window.

Pixels are requested on the product's native grid (computePixels with an affine grid
aligned to it), so Earth Engine performs no resampling.
"""

from datetime import date, datetime, timedelta, timezone

import ee
import numpy as np

from app import config
from app.contracts import Provenance
from app.data.cache import BBox, DateRange
from app.data.sources import (
    ReflectanceComposite,
    SourceError,
    SurfaceTemperatureComposite,
    check_on_grid,
    covering_bounds,
    local_overpass_time,
    season_windows,
)

LANDSAT_COLLECTIONS = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"


def _grid(bounds: tuple[float, float, float, float], crs: str, cell_size_m: float) -> dict:
    min_e, min_n, max_e, max_n = bounds
    return {
        "dimensions": {"width": round((max_e - min_e) / cell_size_m), "height": round((max_n - min_n) / cell_size_m)},
        "affineTransform": {"scaleX": cell_size_m, "shearX": 0, "translateX": min_e,
                            "shearY": 0, "scaleY": -cell_size_m, "translateY": max_n},
        "crsCode": crs,
    }


def _date_filter(date_range: DateRange):
    windows = season_windows(date_range)
    filters = [ee.Filter.date(first.isoformat(), (last + timedelta(days=1)).isoformat()) for first, last in windows]
    return ee.Filter.Or(*filters) if len(filters) > 1 else filters[0]


def _composite_band(pixels: np.ndarray, band: str, count: np.ndarray) -> np.ndarray:
    values = pixels[band].astype(np.float32)
    values[count < config.MIN_CLEAR_OBSERVATIONS] = np.nan
    return values


class EarthEngineSource:
    source_adapter = "earth_engine"

    def __init__(self, project: str) -> None:
        ee.Initialize(project=project)

    def surface_temperature(self, bbox: BBox, date_range: DateRange) -> SurfaceTemperatureComposite:
        check_on_grid(bbox.bounds, config.LANDSAT_CELL_SIZE_M, config.LANDSAT_GRID_ORIGIN_OFFSET_M)
        region = ee.Geometry.Rectangle(list(bbox.bounds), bbox.crs, False)
        searched = ee.ImageCollection(LANDSAT_COLLECTIONS[0]).merge(ee.ImageCollection(LANDSAT_COLLECTIONS[1]))
        searched = (searched.filterBounds(region).filter(_date_filter(date_range))
                    .filter(ee.Filter.lt("CLOUD_COVER", config.SCENE_CLOUD_COVER_MAX_PERCENT)))
        reject_mask = sum(1 << bit for bit in config.LANDSAT_QA_PIXEL_REJECT_BITS)
        c = config.LIANG_2001_OLI_COEFFICIENTS

        def prepare(image):
            st = image.select("ST_B10")
            sr = {name: image.select(band) for name, band in
                  (("blue", "SR_B2"), ("red", "SR_B4"), ("nir", "SR_B5"), ("swir1", "SR_B6"), ("swir2", "SR_B7"))}
            valid = (image.select("QA_PIXEL").bitwiseAnd(reject_mask).eq(0)
                     .And(st.neq(config.LANDSAT_FILL_DN))
                     .And(image.select("ST_QA").multiply(config.LANDSAT_ST_QA_SCALE_K_PER_DN)
                          .lte(config.ST_QA_MAX_UNCERTAINTY_K)))
            for band in sr.values():
                valid = valid.And(band.neq(config.LANDSAT_FILL_DN))
            refl = {k: v.multiply(config.LANDSAT_SR_SCALE_PER_DN).add(config.LANDSAT_SR_OFFSET) for k, v in sr.items()}
            lst_c = (st.multiply(config.LANDSAT_ST_B10_SCALE_K_PER_DN).add(config.LANDSAT_ST_B10_OFFSET_K)
                     .subtract(config.KELVIN_AT_ZERO_CELSIUS).rename("lst_c"))
            albedo = (refl["blue"].multiply(c["blue"]).add(refl["red"].multiply(c["red"]))
                      .add(refl["nir"].multiply(c["nir"])).add(refl["swir1"].multiply(c["swir1"]))
                      .add(refl["swir2"].multiply(c["swir2"])).add(c["intercept"]).rename("albedo"))
            n_valid = valid.rename("v").reduceRegion(ee.Reducer.sum(), region, config.LANDSAT_CELL_SIZE_M, bbox.crs).get("v")
            return lst_c.addBands(albedo).updateMask(valid).set("n_valid", n_valid)

        prepared = searched.map(prepare)
        composite = prepared.median().addBands(prepared.select("lst_c").count().rename("clear_count"))
        pixels = ee.data.computePixels({
            "expression": composite, "fileFormat": "NUMPY_NDARRAY",
            "grid": _grid(bbox.bounds, bbox.crs, config.LANDSAT_CELL_SIZE_M),
        })
        used = prepared.filter(ee.Filter.gt("n_valid", 0))
        meta = ee.Dictionary({
            "ids": used.aggregate_array("LANDSAT_PRODUCT_ID"),
            "times": used.aggregate_array("system:time_start"),
            "platforms": used.aggregate_array("SPACECRAFT_ID"),
            "searched": searched.size(),
        }).getInfo()
        if not meta["ids"]:
            raise SourceError(f"no usable Landsat scenes for {date_range}")

        count = pixels["clear_count"].astype(np.uint16)
        acquired = [datetime.fromtimestamp(ms / 1000, tz=timezone.utc) for ms in meta["times"]]
        provenance = Provenance(
            product="surface_temperature",
            date_range=(date.fromisoformat(date_range.start), date.fromisoformat(date_range.end)),
            months=list(date_range.months),
            scene_count=len(meta["ids"]),
            capture_dates=sorted({dt.date() for dt in acquired}),
            scene_ids=meta["ids"],
            collections=[cid for cid in LANDSAT_COLLECTIONS if any(i.startswith(cid.split("/")[1]) for i in meta["ids"])],
            platforms=sorted(set(meta["platforms"])),
            compositing="per-pixel median",
            cloud_masking=(
                f"scene CLOUD_COVER < {config.SCENE_CLOUD_COVER_MAX_PERCENT}%; "
                "QA_PIXEL fill, dilated cloud, cirrus, cloud and cloud shadow dropped; "
                f"ST_QA uncertainty above {config.ST_QA_MAX_UNCERTAINTY_K} K dropped; "
                f"pixels need at least {config.MIN_CLEAR_OBSERVATIONS} clear observations"
            ),
            overpass_local_time=local_overpass_time(acquired),
            native_resolution_m=config.LANDSAT_TIRS_NATIVE_RESOLUTION_M,
            delivered_resolution_m=config.LANDSAT_CELL_SIZE_M,
            source_adapter=self.source_adapter,
        )
        min_e, _, _, max_n = bbox.bounds
        cell = config.LANDSAT_CELL_SIZE_M
        return SurfaceTemperatureComposite(
            lst_c=_composite_band(pixels, "lst_c", count), albedo=_composite_band(pixels, "albedo", count),
            clear_count=count, crs=bbox.crs, transform=(cell, 0.0, min_e, 0.0, -cell, max_n),
            provenance=provenance, scenes_searched=meta["searched"],
        )

    def land_cover_reflectance(self, bbox: BBox, date_range: DateRange) -> ReflectanceComposite:
        # S2_SR_HARMONIZED has BOA_ADD_OFFSET already removed by Earth Engine for baseline >= 04.00
        # products, so the effective offset here is 0 and must not be applied a second time.
        bounds = covering_bounds(bbox.bounds, config.S2_CELL_SIZE_M)
        region = ee.Geometry.Rectangle(list(bounds), bbox.crs, False)
        searched = (ee.ImageCollection(S2_COLLECTION).filterBounds(region).filter(_date_filter(date_range))
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.SCENE_CLOUD_COVER_MAX_PERCENT)))

        def prepare(image):
            red, nir = image.select("B4"), image.select("B8")
            valid = (image.select("SCL").remap(list(config.S2_SCL_REJECT_CLASSES),
                                               [0] * len(config.S2_SCL_REJECT_CLASSES), 1)
                     .And(red.neq(config.S2_NODATA_DN)).And(nir.neq(config.S2_NODATA_DN)))
            n_valid = valid.rename("v").reduceRegion(ee.Reducer.sum(), region, config.S2_CELL_SIZE_M, bbox.crs).get("v")
            reflectance = red.addBands(nir).divide(config.S2_HARMONIZED_QUANTIFICATION_VALUE).rename(["red", "nir"])
            return reflectance.updateMask(valid).set("n_valid", n_valid)

        prepared = searched.map(prepare)
        composite = prepared.median().addBands(prepared.select("red").count().rename("clear_count"))
        pixels = ee.data.computePixels({
            "expression": composite, "fileFormat": "NUMPY_NDARRAY",
            "grid": _grid(bounds, bbox.crs, config.S2_CELL_SIZE_M),
        })
        used = prepared.filter(ee.Filter.gt("n_valid", 0))
        meta = ee.Dictionary({
            "ids": used.aggregate_array("PRODUCT_ID"),
            "times": used.aggregate_array("system:time_start"),
            "platforms": used.aggregate_array("SPACECRAFT_NAME"),
            "searched": searched.size(),
        }).getInfo()
        if not meta["ids"]:
            raise SourceError(f"no usable Sentinel-2 scenes for {date_range}")

        count = pixels["clear_count"].astype(np.uint16)
        acquired = [datetime.fromtimestamp(ms / 1000, tz=timezone.utc) for ms in meta["times"]]
        provenance = Provenance(
            product="land_cover",
            date_range=(date.fromisoformat(date_range.start), date.fromisoformat(date_range.end)),
            months=list(date_range.months),
            scene_count=len(meta["ids"]),
            capture_dates=sorted({dt.date() for dt in acquired}),
            scene_ids=meta["ids"],
            collections=[S2_COLLECTION],
            platforms=sorted(set(meta["platforms"])),
            compositing="per-pixel median",
            cloud_masking=(
                f"scene CLOUDY_PIXEL_PERCENTAGE < {config.SCENE_CLOUD_COVER_MAX_PERCENT}%; "
                f"SCL classes {', '.join(str(c) for c in config.S2_SCL_REJECT_CLASSES)} dropped; "
                "BOA_ADD_OFFSET removed by Earth Engine harmonisation; "
                f"pixels need at least {config.MIN_CLEAR_OBSERVATIONS} clear observations"
            ),
            overpass_local_time=local_overpass_time(acquired),
            native_resolution_m=config.S2_CELL_SIZE_M,
            delivered_resolution_m=config.S2_CELL_SIZE_M,
            source_adapter=self.source_adapter,
        )
        cell = config.S2_CELL_SIZE_M
        return ReflectanceComposite(
            red=_composite_band(pixels, "red", count), nir=_composite_band(pixels, "nir", count),
            clear_count=count, crs=bbox.crs, transform=(cell, 0.0, bounds[0], 0.0, -cell, bounds[3]),
            provenance=provenance, scenes_searched=meta["searched"],
            boa_add_offset_applied=True, boa_add_offsets_seen=[0.0],
        )
