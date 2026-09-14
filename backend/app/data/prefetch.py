"""CLI: pull and cache Landsat and Sentinel-2 for a street's 2 km window, in one run.

First run for a street (writes backend/fixtures/streets/<id>.json):

    python -m app.data.prefetch --street pune-fc-road --name "FC Road, Pune" --city Pune \
        --profile dense_commercial --bbox-street 73.8401 18.5181 73.8437 18.5228

Later runs read the street's manifest:

    python -m app.data.prefetch --street pune-fc-road

This CLI's job is to fill the cache, so cache misses are allowed to reach the network
regardless of USE_LIVE_DATA. Every read still goes through app/data/cache.py, so a
second run is served entirely from disk.
"""

import argparse
import json
import math
import sys

import numpy as np
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds

from app import config
from app.data.cache import BBox, CachedResult, CacheKey, DateRange, cache_path, get_or_fetch, load
from app.data.fixtures import LANDSAT_PRODUCT, S2_PRODUCT
from app.data.footprints import load_overture_buildings, merge_footprints, overture_key
from app.data.osm import load_city_ways, load_osm, load_places, osm_key


def utm_epsg(lon: float, lat: float) -> str:
    zone = math.floor((lon + 180) / 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def landsat_window(center_lon: float, center_lat: float, cells: int) -> BBox:
    """A cells x cells window on the Landsat 30 m grid, centred as closely as the grid allows."""
    crs = utm_epsg(center_lon, center_lat)
    (e,), (n,) = warp_transform("EPSG:4326", crs, [center_lon], [center_lat])
    cell, offset = config.LANDSAT_CELL_SIZE_M, config.LANDSAT_GRID_ORIGIN_OFFSET_M
    half = cells * cell / 2
    min_e = offset + cell * round((e - half - offset) / cell)
    max_n = offset + cell * round((n + half - offset) / cell)
    return BBox(crs=crs, bounds=(min_e, max_n - cells * cell, min_e + cells * cell, max_n))


def make_source(adapter: str):
    if adapter == "planetary_computer":
        from app.data.planetary import PlanetaryComputerSource
        return PlanetaryComputerSource()
    if adapter == "earth_engine":
        if not config.EARTH_ENGINE_PROJECT:
            sys.exit("Earth Engine adapter selected but EARTH_ENGINE_PROJECT is not set.")
        from app.data.earth_engine import EarthEngineSource
        return EarthEngineSource(config.EARTH_ENGINE_PROJECT)
    sys.exit(f"Unknown source adapter {adapter!r}.")


def fetch_landsat(source, bbox: BBox, date_range: DateRange):
    def fetch() -> CachedResult:
        composite = source.surface_temperature(bbox, date_range)
        return CachedResult(
            arrays={"lst_c": composite.lst_c, "albedo": composite.albedo, "clear_count": composite.clear_count},
            metadata={"crs": composite.crs, "transform": list(composite.transform),
                      "scenes_searched": composite.scenes_searched,
                      "provenance": composite.provenance.model_dump(mode="json")},
        )
    return fetch


def fetch_sentinel2(source, bbox: BBox, date_range: DateRange):
    def fetch() -> CachedResult:
        composite = source.land_cover_reflectance(bbox, date_range)
        return CachedResult(
            arrays={"red": composite.red, "nir": composite.nir, "clear_count": composite.clear_count},
            metadata={"crs": composite.crs, "transform": list(composite.transform),
                      "scenes_searched": composite.scenes_searched,
                      "boa_add_offset_applied": composite.boa_add_offset_applied,
                      "boa_add_offsets_seen": composite.boa_add_offsets_seen,
                      "provenance": composite.provenance.model_dump(mode="json")},
        )
    return fetch


def load_or_create_manifest(args) -> dict:
    path = config.STREETS_DIR / f"{args.street}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    missing = [flag for flag, value in (("--name", args.name), ("--city", args.city), ("--profile", args.profile),
                                        ("--bbox-street", args.bbox_street)) if value is None]
    if missing:
        sys.exit(f"No manifest for {args.street}; first run needs {', '.join(missing)}.")
    return {
        "id": args.street,
        "name": args.name,
        "city": args.city,
        "profile": args.profile,
        "bbox_street": list(args.bbox_street),
        "bbox_street_verified": False,
    }


def describe(values: np.ndarray) -> str:
    finite = values[np.isfinite(values)]
    return f"{finite.min():.2f} / {finite.max():.2f} / {finite.mean():.2f}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--street", required=True)
    parser.add_argument("--name")
    parser.add_argument("--city")
    parser.add_argument("--profile")
    parser.add_argument("--bbox-street", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    parser.add_argument("--adapter", default=config.ACTIVE_SOURCE_ADAPTER)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    manifest = load_or_create_manifest(args)
    min_lon, min_lat, max_lon, max_lat = manifest["bbox_street"]
    window = landsat_window((min_lon + max_lon) / 2, (min_lat + max_lat) / 2, config.WINDOW_CELLS)
    date_range = DateRange(start=config.SEASON_START, end=config.SEASON_END, months=config.SEASON_MONTHS)
    landsat_key = CacheKey(args.adapter, LANDSAT_PRODUCT, window, date_range)
    s2_key = CacheKey(args.adapter, S2_PRODUCT, window, date_range)

    was_cached = {"landsat": load(landsat_key) is not None, "s2": load(s2_key) is not None}
    source = None if all(was_cached.values()) else make_source(args.adapter)
    landsat = get_or_fetch(landsat_key, fetch_landsat(source, window, date_range), allow_network=True)
    s2 = get_or_fetch(s2_key, fetch_sentinel2(source, window, date_range), allow_network=True)
    osm = load_osm(window, allow_network=True)
    overture = load_overture_buildings(window, allow_network=True)
    merged, footprint_counts = merge_footprints(osm["buildings"], overture["buildings"])
    city_ways = load_city_ways(manifest["city"], window.crs, allow_network=True)
    places = load_places(window, allow_network=True)

    manifest.update({
        "bbox_window": [round(v, 5) for v in transform_bounds(window.crs, "EPSG:4326", *window.bounds)],
        "window": {"crs": window.crs, "bounds_m": list(window.bounds), "shape": [config.WINDOW_CELLS] * 2},
        "date_range": {"start": date_range.start, "end": date_range.end, "months": list(date_range.months)},
        "source_adapter": args.adapter,
        "cache": {
            "surface_temperature": str(cache_path(landsat_key).relative_to(config.BACKEND_DIR).as_posix()),
            "land_cover": str(cache_path(s2_key).relative_to(config.BACKEND_DIR).as_posix()),
            "osm": str(cache_path(osm_key(window)).relative_to(config.BACKEND_DIR).as_posix()),
            "overture_buildings": str(cache_path(overture_key(window)).relative_to(config.BACKEND_DIR).as_posix()),
        },
    })
    config.STREETS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STREETS_DIR / f"{args.street}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lst_c, albedo, clear = landsat.arrays["lst_c"], landsat.arrays["albedo"], landsat.arrays["clear_count"]
    lp, sp = landsat.metadata["provenance"], s2.metadata["provenance"]
    print(f"Street       {manifest['id']} ({manifest['name']}), bbox_street_verified={manifest['bbox_street_verified']}")
    print(f"Window       {window.crs} {list(window.bounds)} m, {lst_c.shape[0]} x {lst_c.shape[1]} cells at 30 m")
    print(f"             display bbox (WGS84) {manifest['bbox_window']}")
    print(f"Adapter      {args.adapter}; Landsat {'from cache' if was_cached['landsat'] else 'fetched'}, "
          f"Sentinel-2 {'from cache' if was_cached['s2'] else 'fetched'}")
    print()
    print("Land surface temperature, Landsat C2 L2 ST_B10, per-pixel median (measured, 30 m delivered, 100 m native)")
    print(f"  min / max / mean     {describe(lst_c)} °C")
    print(f"  valid pixels         {int(np.isfinite(lst_c).sum())} of {lst_c.size}")
    print(f"  clear obs per pixel  min {int(clear.min())}, median {int(np.median(clear))}, max {int(clear.max())}")
    print(f"  scenes               {lp['scene_count']} used of {landsat.metadata['scenes_searched']} searched")
    print(f"  date range           {lp['date_range'][0]} to {lp['date_range'][1]}, months {lp['months']}; "
          f"captures {lp['capture_dates'][0]} to {lp['capture_dates'][-1]}")
    print(f"  collections          {lp['collections']} platforms {lp['platforms']}")
    print(f"  overpass             {lp['overpass_local_time']} IST (median acquisition time)")
    print(f"  broadband albedo     min / max / mean {describe(albedo)}")
    print()
    red, nir = s2.arrays["red"], s2.arrays["nir"]
    print("Surface reflectance, Sentinel-2 L2A B4 and B8, per-pixel median (10 m)")
    print(f"  grid                 {red.shape[0]} x {red.shape[1]} cells")
    print(f"  valid pixels         {int(np.isfinite(red).sum())} of {red.size}")
    print(f"  red B4 min/max/mean  {describe(red)}")
    print(f"  NIR B8 min/max/mean  {describe(nir)}")
    print(f"  scenes               {sp['scene_count']} used of {s2.metadata['scenes_searched']} searched")
    print(f"  date range           {sp['date_range'][0]} to {sp['date_range'][1]}, months {sp['months']}; "
          f"captures {sp['capture_dates'][0]} to {sp['capture_dates'][-1]}")
    print(f"  collections          {sp['collections']} platforms {sp['platforms']}")
    print(f"  BOA_ADD_OFFSET       applied={s2.metadata['boa_add_offset_applied']}, "
          f"values seen {s2.metadata['boa_add_offsets_seen']}")
    print()
    print("OpenStreetMap, Overpass")
    print(f"  database timestamp   {osm['osm_base']}")
    print(f"  buildings            {len(osm['buildings'])}")
    print(f"  highway ways         {len(osm['highways'])}")
    print(f"  named places         {len(places['places'])} (database timestamp {places['osm_base']})")
    print()
    print(f"Building footprints, OSM unioned with Overture {overture['release']} non-OSM footprints")
    print(f"  Overture rows        {len(overture['buildings'])}")
    print(f"  merged buildings     {len(merged)}  {footprint_counts}")
    print()
    print(f"City locator, {manifest['city']}: major roads and rivers, Overpass")
    print(f"  database timestamp   {city_ways['osm_base']}")
    print(f"  ways                 {len(city_ways['ways'])}")


if __name__ == "__main__":
    main()
