"""Disk cache for every external data call, keyed on (source_adapter, product, bbox, date_range).

Arrays are stored as .npy and metadata as meta.json, one directory per key under
backend/fixtures/cache/. Re-running the same street never re-hits the network, and
with USE_LIVE_DATA false a cache miss raises instead of fetching (CLAUDE.md rule 4).
"""

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from app import config


@dataclass(frozen=True)
class BBox:
    """Window bounds [min_x, min_y, max_x, max_y] in the units of `crs` (metres for UTM)."""

    crs: str
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class DateRange:
    """Inclusive ISO dates, restricted to `months` in every year of the range."""

    start: str
    end: str
    months: tuple[int, ...]


@dataclass(frozen=True)
class CacheKey:
    source_adapter: str
    product: str
    bbox: BBox
    date_range: DateRange

    def as_dict(self) -> dict:
        data = asdict(self)
        data["bbox"]["bounds"] = [round(v, 3) for v in self.bbox.bounds]
        data["date_range"]["months"] = list(self.date_range.months)
        return data

    def digest(self) -> str:
        canonical = json.dumps(self.as_dict(), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class CachedResult:
    arrays: dict[str, np.ndarray]
    metadata: dict = field(default_factory=dict)


class CacheMiss(RuntimeError):
    """Nothing cached for this key and live data is disabled."""


def cache_path(key: CacheKey, root: Path | None = None) -> Path:
    return (root or config.CACHE_DIR) / key.source_adapter / key.product / key.digest()


def load(key: CacheKey, root: Path | None = None) -> CachedResult | None:
    directory = cache_path(key, root)
    meta_file = directory / "meta.json"
    if not meta_file.exists():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta["key"] != key.as_dict():
        raise RuntimeError(f"cache key mismatch in {directory}")
    arrays = {name: np.load(directory / f"{name}.npy", allow_pickle=False) for name in meta["arrays"]}
    return CachedResult(arrays=arrays, metadata=meta["metadata"])


def store(key: CacheKey, result: CachedResult, root: Path | None = None) -> Path:
    directory = cache_path(key, root)
    staging = directory.with_name(directory.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name, array in result.arrays.items():
        np.save(staging / f"{name}.npy", array, allow_pickle=False)
    meta = {
        "key": key.as_dict(),
        "stored_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arrays": {name: {"dtype": str(a.dtype), "shape": list(a.shape)} for name, a in result.arrays.items()},
        "metadata": result.metadata,
    }
    (staging / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if directory.exists():
        shutil.rmtree(directory)
    staging.rename(directory)
    return directory


def get_or_fetch(
    key: CacheKey,
    fetch: Callable[[], CachedResult],
    *,
    allow_network: bool | None = None,
    root: Path | None = None,
) -> CachedResult:
    """Return the cached result for `key`, fetching and storing it only if network use is allowed.

    `allow_network` defaults to config.USE_LIVE_DATA. The prefetch CLI passes True explicitly.
    """
    cached = load(key, root)
    if cached is not None:
        return cached
    if allow_network is None:
        allow_network = config.USE_LIVE_DATA
    if not allow_network:
        raise CacheMiss(
            f"No cached {key.product} from {key.source_adapter} for bbox {key.bbox.bounds} "
            f"({key.bbox.crs}), dates {key.date_range.start}..{key.date_range.end}, and USE_LIVE_DATA is false."
        )
    result = fetch()
    store(key, result, root)
    return result
