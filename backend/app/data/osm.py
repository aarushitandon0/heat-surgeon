"""OSM Overpass queries: building footprints and highway ways for a street's window.

Goes through app/data/cache.py like every external call. Coordinates are stored in the
window's UTM CRS, in metres. Map data © OpenStreetMap contributors, ODbL 1.0.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds

from app import config
from app.data.cache import BBox, CachedResult, CacheKey, DateRange, get_or_fetch
from app.data.sources import SourceError

# The main instance first; a public mirror serving the same database when the main one times out
# (it answered 504 to the city locator query on 2026-09-14).
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
SOURCE_ADAPTER = "overpass"
PRODUCT = "osm_buildings_highways"
KEPT_TAGS = (
    "building", "building:levels", "height", "highway", "name", "name:en", "alt_name", "official_name",
    "width", "lanes", "sidewalk", "sidewalk:width", "sidewalk:both:width", "sidewalk:left:width",
    "sidewalk:right:width", "surface", "oneway", "footway", "area",
)


def overpass_query(bounds_wgs84: tuple[float, float, float, float]) -> str:
    west, south, east, north = bounds_wgs84
    box = f"{south},{west},{north},{east}"
    return (
        "[out:json][timeout:180];"
        f'(way["building"]({box});relation["building"]["type"="multipolygon"]({box});way["highway"]({box}););'
        "out geom;"
    )


def _to_utm(geometry: list[dict], crs: str) -> list[list[float]]:
    eastings, northings = warp_transform("EPSG:4326", crs, [p["lon"] for p in geometry], [p["lat"] for p in geometry])
    return [[round(e, 2), round(n, 2)] for e, n in zip(eastings, northings)]


def _closed(coords: list[list[float]]) -> bool:
    return len(coords) >= 4 and coords[0] == coords[-1]


def parse_overpass(payload: dict, crs: str) -> dict:
    """Overpass JSON to {buildings, highways, skipped, osm_base}. Buildings keep closed outer rings only."""
    buildings, highways = [], []
    skipped = {"open_building_rings": 0}
    for element in payload.get("elements", []):
        all_tags = element.get("tags", {})
        tags = {k: v for k, v in all_tags.items() if k in KEPT_TAGS}
        osm_id = f"osm:{element['type']}/{element['id']}"
        if element["type"] == "way" and element.get("geometry"):
            coords = _to_utm(element["geometry"], crs)
            if "building" in all_tags:
                if _closed(coords):
                    buildings.append({"id": osm_id, "tags": tags, "rings": [coords]})
                else:
                    skipped["open_building_rings"] += 1
            elif "highway" in all_tags:
                highways.append({"id": osm_id, "tags": tags, "coords": coords})
        elif element["type"] == "relation":
            rings = []
            for member in element.get("members", []):
                if member.get("role") == "outer" and member.get("geometry"):
                    coords = _to_utm(member["geometry"], crs)
                    if _closed(coords):
                        rings.append(coords)
                    else:
                        skipped["open_building_rings"] += 1
            if rings:
                buildings.append({"id": osm_id, "tags": tags, "rings": rings})
    return {
        "osm_base": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "attribution": "Map data © OpenStreetMap contributors, ODbL 1.0",
        "buildings": buildings,
        "highways": highways,
        "skipped": skipped,
    }


def _post_overpass(query: str) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_error = None
    for attempt in range(4):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        request = urllib.request.Request(url, data=body,
                                         headers={"User-Agent": "heat-surgeon/0.1 (hackathon research prototype)"})
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(15 * (attempt + 1))
    raise SourceError(f"Overpass did not respond: {last_error}")


def osm_key(bbox: BBox) -> CacheKey:
    snapshot = config.OSM_SNAPSHOT_DATE
    return CacheKey(SOURCE_ADAPTER, PRODUCT, bbox, DateRange(start=snapshot, end=snapshot, months=()))


def load_osm(bbox: BBox, allow_network: bool | None = None) -> dict:
    """Buildings and highways intersecting `bbox`, from cache or (if allowed) from Overpass."""
    def fetch() -> CachedResult:
        bounds_wgs84 = transform_bounds(bbox.crs, "EPSG:4326", *bbox.bounds)
        return CachedResult(arrays={}, metadata=parse_overpass(_post_overpass(overpass_query(bounds_wgs84)), bbox.crs))
    return get_or_fetch(osm_key(bbox), fetch, allow_network=allow_network).metadata


# --- City locator: major roads and rivers at city scale, for display only ---------------------

CITY_PRODUCT = "osm_city_major_roads_rivers"


def city_overpass_query(bounds_wgs84: tuple[float, float, float, float]) -> str:
    west, south, east, north = bounds_wgs84
    box = f"{south},{west},{north},{east}"
    classes = "|".join(config.CITY_LOCATOR_HIGHWAY_CLASSES)
    return (
        "[out:json][timeout:180];"
        f'(way["highway"~"^({classes})$"]({box});way["waterway"="river"]({box}););'
        "out geom;"
    )


def parse_city_ways(payload: dict, crs: str) -> dict:
    """Overpass JSON to {ways: [{id, kind, name, coords}], osm_base}. kind is the highway or waterway value verbatim."""
    ways = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        kind = tags.get("highway") or tags.get("waterway")
        if element["type"] != "way" or not element.get("geometry") or kind is None:
            continue
        ways.append({"id": f"osm:way/{element['id']}", "kind": kind, "name": tags.get("name:en") or tags.get("name"),
                     "coords": _to_utm(element["geometry"], crs)})
    return {
        "osm_base": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "attribution": "Map data © OpenStreetMap contributors, ODbL 1.0",
        "ways": ways,
    }


def city_bbox(city: str, crs: str) -> BBox:
    bounds = transform_bounds("EPSG:4326", crs, *config.CITY_LOCATOR_BOUNDS_WGS84[city])
    return BBox(crs=crs, bounds=tuple(round(v, 1) for v in bounds))


def load_city_ways(city: str, crs: str, allow_network: bool | None = None) -> dict:
    """Major roads and rivers across the city's locator extent, from cache or (if allowed) from Overpass."""
    bbox = city_bbox(city, crs)
    snapshot = config.OSM_SNAPSHOT_DATE
    key = CacheKey(SOURCE_ADAPTER, CITY_PRODUCT, bbox, DateRange(start=snapshot, end=snapshot, months=()))

    def fetch() -> CachedResult:
        query = city_overpass_query(config.CITY_LOCATOR_BOUNDS_WGS84[city])
        return CachedResult(arrays={}, metadata=parse_city_ways(_post_overpass(query), crs))
    return get_or_fetch(key, fetch, allow_network=allow_network).metadata
