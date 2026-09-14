"""Building footprints: OpenStreetMap unioned with Overture's non-OSM footprints (Microsoft, Google).

OSM misses many roofs in Pune (docs/methodology.md). Overture's buildings theme already conflates OSM,
Microsoft ML Buildings and Google Open Buildings; we take only its non-OSM footprints, because OSM comes
from our own Overpass pull, and drop any that duplicate an OSM building by centroid.

The Overture read goes through app/data/cache.py like every external call. Coordinates are stored in the
window's UTM CRS, in metres. Footprints from Overture: © OpenStreetMap contributors (ODbL), Microsoft
(ODbL), Google (CC BY 4.0 / ODbL), as redistributed by Overture Maps Foundation.
"""

from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from shapely import STRtree
from shapely.geometry import Point, Polygon

from app import config
from app.data.cache import BBox, CachedResult, CacheKey, DateRange, get_or_fetch

SOURCE_ADAPTER = "overture"
PRODUCT = "buildings"
OSM_DATASET = "OpenStreetMap"
GOOGLE_DATASET = "Google Open Buildings"


def overture_key(bbox: BBox) -> CacheKey:
    release = config.OVERTURE_RELEASE
    return CacheKey(SOURCE_ADAPTER, PRODUCT, bbox, DateRange(start=release, end=release, months=()))


def _rings_to_utm(geometry, crs: str) -> list[list[list[float]]]:
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    rings = []
    for polygon in polygons:
        lons, lats = zip(*polygon.exterior.coords)
        eastings, northings = warp_transform("EPSG:4326", crs, list(lons), list(lats))
        rings.append([[round(e, 2), round(n, 2)] for e, n in zip(eastings, northings)])
    return rings


def _fetch_overture(bbox: BBox) -> CachedResult:
    import duckdb
    from shapely import wkb

    west, south, east, north = transform_bounds(bbox.crs, "EPSG:4326", *bbox.bounds)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    con.execute(f"SET s3_region='{config.OVERTURE_S3_REGION}'")
    rows = con.execute(
        f"""
        SELECT id, sources[1].dataset, sources[1].confidence, ST_AsWKB(geometry)
        FROM read_parquet('{config.OVERTURE_BUILDINGS_PARQUET}')
        WHERE bbox.xmin < ? AND bbox.xmax > ? AND bbox.ymin < ? AND bbox.ymax > ?
        """,
        [east, west, north, south],
    ).fetchall()
    buildings = [
        {"id": f"overture:{overture_id}", "dataset": dataset, "confidence": confidence,
         "rings": _rings_to_utm(wkb.loads(bytes(geometry)), bbox.crs)}
        for overture_id, dataset, confidence, geometry in rows
    ]
    return CachedResult(arrays={}, metadata={
        "release": config.OVERTURE_RELEASE,
        "attribution": "Overture Maps Foundation buildings theme: OpenStreetMap (ODbL), Microsoft ML Buildings "
                       "(ODbL), Google Open Buildings (CC BY 4.0 / ODbL)",
        "buildings": buildings,
    })


def load_overture_buildings(bbox: BBox, allow_network: bool | None = None) -> dict:
    """Overture footprints intersecting `bbox`, from cache or (if allowed) from Overture's public S3 GeoParquet."""
    return get_or_fetch(overture_key(bbox), lambda: _fetch_overture(bbox), allow_network=allow_network).metadata


def merge_footprints(osm_buildings: list[dict], overture_buildings: list[dict]) -> tuple[list[dict], dict]:
    """OSM footprints plus non-duplicate, confident non-OSM Overture footprints.

    Returns (buildings, counts). Each building is {id, rings, footprint_source}, footprint_source verbatim
    from the dataset name.
    """
    merged = [{"id": b["id"], "rings": b["rings"], "footprint_source": OSM_DATASET} for b in osm_buildings]
    osm_polygons = [Polygon(ring) for b in osm_buildings for ring in b["rings"]]
    osm_polygons = [p if p.is_valid else p.buffer(0) for p in osm_polygons]
    tree = STRtree(osm_polygons)
    centroids = [p.centroid for p in osm_polygons]
    centroid_tree = STRtree(centroids)

    counts = {"osm": len(osm_buildings), "overture_osm_skipped": 0, "low_confidence": 0, "duplicate": 0}
    for building in overture_buildings:
        dataset = building["dataset"]
        if dataset == OSM_DATASET:
            counts["overture_osm_skipped"] += 1
            continue
        if (dataset == GOOGLE_DATASET and building["confidence"] is not None
                and building["confidence"] < config.GOOGLE_OPEN_BUILDINGS_MIN_CONFIDENCE):
            counts["low_confidence"] += 1
            continue
        centroid = Polygon(building["rings"][0]).centroid
        inside = any(osm_polygons[i].contains(centroid) for i in tree.query(centroid))
        near = len(centroid_tree.query(centroid.buffer(config.FOOTPRINT_DEDUPE_DISTANCE_M))) > 0
        if inside or near:
            counts["duplicate"] += 1
            continue
        merged.append({"id": building["id"], "rings": building["rings"], "footprint_source": dataset})
        counts[dataset] = counts.get(dataset, 0) + 1
    return merged, counts
