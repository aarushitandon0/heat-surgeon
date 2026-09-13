"""Loads pre-cached streets from backend/fixtures/ through the disk cache. Never touches the network."""

import json
from dataclasses import dataclass

from app import config
from app.contracts import Provenance
from app.data.cache import BBox, CachedResult, CacheKey, DateRange, get_or_fetch
from app.data.osm import load_osm

LANDSAT_PRODUCT = "landsat_c2_l2_composite"
S2_PRODUCT = "sentinel_2_l2a_composite"


@dataclass
class CachedWindow:
    manifest: dict
    landsat: CachedResult
    sentinel2: CachedResult
    osm: dict

    @property
    def bbox(self) -> BBox:
        return BBox(crs=self.manifest["window"]["crs"], bounds=tuple(self.manifest["window"]["bounds_m"]))

    @property
    def landsat_provenance(self) -> Provenance:
        return Provenance(**self.landsat.metadata["provenance"])

    @property
    def sentinel2_provenance(self) -> Provenance:
        return Provenance(**self.sentinel2.metadata["provenance"])


def street_manifest(street_id: str) -> dict:
    path = config.STREETS_DIR / f"{street_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No fixture manifest for {street_id}. Run: python -m app.data.prefetch --street {street_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def window_keys(manifest: dict) -> tuple[CacheKey, CacheKey]:
    window = manifest["window"]
    bbox = BBox(crs=window["crs"], bounds=tuple(window["bounds_m"]))
    dates = manifest["date_range"]
    date_range = DateRange(start=dates["start"], end=dates["end"], months=tuple(dates["months"]))
    adapter = manifest["source_adapter"]
    return CacheKey(adapter, LANDSAT_PRODUCT, bbox, date_range), CacheKey(adapter, S2_PRODUCT, bbox, date_range)


def _never_fetch() -> CachedResult:
    raise AssertionError("fixtures never fetch")


def load_window(street_id: str) -> CachedWindow:
    """The street's cached 2 km window. Raises CacheMiss if it was never prefetched."""
    manifest = street_manifest(street_id)
    landsat_key, s2_key = window_keys(manifest)
    return CachedWindow(
        manifest=manifest,
        landsat=get_or_fetch(landsat_key, _never_fetch, allow_network=False),
        sentinel2=get_or_fetch(s2_key, _never_fetch, allow_network=False),
        osm=load_osm(landsat_key.bbox, allow_network=False),
    )
