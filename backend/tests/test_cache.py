"""Disk cache: offline misses raise, live misses fetch once, arrays round-trip exactly.

Arrays here are synthetic test fixtures, not data.
"""

import importlib

import numpy as np
import pytest

from app import config
from app.data.cache import BBox, CachedResult, CacheKey, CacheMiss, DateRange, get_or_fetch, load


def key(**overrides):
    fields = {
        "source_adapter": "planetary_computer",
        "product": "landsat_c2_l2_composite",
        "bbox": BBox(crs="EPSG:32643", bounds=(376755.0, 2047155.0, 378765.0, 2049165.0)),
        "date_range": DateRange(start="2024-03-01", end="2026-05-31", months=(3, 4, 5)),
    }
    return CacheKey(**{**fields, **overrides})


class CountingFetch:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        grid = np.array([[30.5, np.nan], [31.25, 29.0]], dtype=np.float32)
        return CachedResult(arrays={"lst_c": grid, "clear_count": np.array([[3, 0], [4, 5]], dtype=np.uint8)},
                            metadata={"scene_ids": ["scene-a"]})


def test_offline_miss_raises_without_fetching(tmp_path):
    fetch = CountingFetch()
    with pytest.raises(CacheMiss, match="USE_LIVE_DATA is false"):
        get_or_fetch(key(), fetch, allow_network=False, root=tmp_path)
    assert fetch.calls == 0


def test_live_miss_fetches_once_then_serves_from_disk(tmp_path):
    fetch = CountingFetch()
    get_or_fetch(key(), fetch, allow_network=True, root=tmp_path)
    again = get_or_fetch(key(), fetch, allow_network=False, root=tmp_path)
    assert fetch.calls == 1
    assert again.metadata == {"scene_ids": ["scene-a"]}


def test_arrays_round_trip_exactly_including_nan(tmp_path):
    original = CountingFetch()()
    get_or_fetch(key(), lambda: original, allow_network=True, root=tmp_path)
    loaded = load(key(), root=tmp_path)
    np.testing.assert_array_equal(loaded.arrays["lst_c"], original.arrays["lst_c"])
    assert loaded.arrays["lst_c"].dtype == np.float32
    assert loaded.arrays["clear_count"].dtype == np.uint8


def test_each_key_component_separates_entries(tmp_path):
    get_or_fetch(key(), CountingFetch(), allow_network=True, root=tmp_path)
    variants = [
        key(source_adapter="earth_engine"),
        key(product="sentinel_2_l2a_composite"),
        key(bbox=BBox(crs="EPSG:32643", bounds=(376785.0, 2047155.0, 378795.0, 2049165.0))),
        key(date_range=DateRange(start="2024-03-01", end="2026-05-31", months=(4, 5))),
    ]
    for variant in variants:
        assert load(variant, root=tmp_path) is None


def test_use_live_data_defaults_to_false(monkeypatch):
    monkeypatch.delenv("USE_LIVE_DATA", raising=False)
    assert importlib.reload(config).USE_LIVE_DATA is False
    monkeypatch.setenv("USE_LIVE_DATA", "true")
    assert importlib.reload(config).USE_LIVE_DATA is True
    monkeypatch.delenv("USE_LIVE_DATA")
    importlib.reload(config)
