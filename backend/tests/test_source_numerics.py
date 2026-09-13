"""Shared scaling, masking and compositing in app/data/sources.py, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

from datetime import date, datetime, timezone

import numpy as np
import pytest

from app.data.cache import DateRange
from app.data.sources import (
    SourceError,
    check_on_grid,
    covering_bounds,
    liang_broadband_albedo,
    local_overpass_time,
    median_composite,
    qa_pixel_clear,
    s2_reflectance,
    scl_clear,
    season_windows,
    sr_to_reflectance,
    st_qa_to_kelvin,
)


def test_check_on_grid_accepts_landsat_edges_and_rejects_off_grid():
    check_on_grid((376755.0, 2047155.0, 378765.0, 2049165.0), 30.0, 15.0)  # all 15 + 30k
    with pytest.raises(SourceError, match="refusing to resample"):
        check_on_grid((376760.0, 2047155.0, 378765.0, 2049165.0), 30.0, 15.0)


def test_covering_bounds_expands_outward_to_the_grid():
    # Landsat edges at ...55 and ...65 expand to the 10 m grid at ...50 and ...70
    assert covering_bounds((376755.0, 2047155.0, 378765.0, 2049165.0), 10.0) == (376750, 2047150, 378770, 2049170)


def test_season_windows_one_per_year_inclusive():
    windows = season_windows(DateRange(start="2024-03-01", end="2026-05-31", months=(3, 4, 5)))
    assert windows == [
        (date(2024, 3, 1), date(2024, 5, 31)),
        (date(2025, 3, 1), date(2025, 5, 31)),
        (date(2026, 3, 1), date(2026, 5, 31)),
    ]


def test_local_overpass_time_is_median_utc_plus_ist_offset():
    # median of 05:27 and 05:29 UTC is 05:28; plus 5 h 30 min is 10:58
    acquired = [datetime(2025, 4, 1, 5, 27, tzinfo=timezone.utc), datetime(2025, 4, 9, 5, 29, tzinfo=timezone.utc)]
    assert local_overpass_time(acquired) == "10:58"


def test_landsat_surface_reflectance_scaling():
    # 10000 * 0.0000275 = 0.275; 0.275 - 0.2 = 0.075
    result = sr_to_reflectance(np.array([10000, 0], dtype=np.uint16))
    assert np.isclose(result[0], 0.075)
    assert np.isnan(result[1])


def test_st_qa_uncertainty_scaling():
    # 250 * 0.01 = 2.5 K
    result = st_qa_to_kelvin(np.array([250, -9999], dtype=np.int16))
    assert np.isclose(result[0], 2.5)
    assert np.isnan(result[1])


def test_qa_pixel_rejects_fill_dilated_cirrus_cloud_shadow_only():
    clear_bit, water_bit, snow_bit = 1 << 6, 1 << 7, 1 << 5
    values = np.array([
        clear_bit,             # clear
        clear_bit | water_bit, # water, kept
        snow_bit,              # snow, kept (not in the reject set)
        1 << 0,                # fill
        1 << 1,                # dilated cloud
        1 << 2,                # cirrus
        1 << 3,                # cloud
        1 << 4,                # cloud shadow
    ], dtype=np.uint16)
    assert qa_pixel_clear(values).tolist() == [True, True, True, False, False, False, False, False]


def test_liang_albedo_for_uniform_reflectance():
    # 0.2 * (0.356 + 0.130 + 0.373 + 0.085 + 0.072) - 0.0018 = 0.2 * 1.016 - 0.0018 = 0.2014
    r = np.array([0.2])
    assert np.isclose(liang_broadband_albedo(r, r, r, r, r)[0], 0.2014)


def test_s2_reflectance_applies_boa_offset_from_metadata():
    # (2000 - 1000) / 10000 = 0.1 ; (2000 + 0) / 10000 = 0.2 before baseline 04.00
    assert np.isclose(s2_reflectance(np.array([2000]), -1000, 10000)[0], 0.1)
    assert np.isclose(s2_reflectance(np.array([2000]), 0, 10000)[0], 0.2)
    assert np.isnan(s2_reflectance(np.array([0]), -1000, 10000)[0])


def test_scl_rejects_no_data_shadow_cloud_cirrus():
    classes = np.array([0, 3, 4, 5, 6, 8, 9, 10, 11])
    assert scl_clear(classes).tolist() == [False, False, True, True, True, False, False, False, True]


def test_median_composite_uses_only_valid_observations_and_enforces_minimum():
    stack = np.array([[[1.0, 10.0]], [[5.0, 20.0]], [[3.0, 99.0]]])       # 3 scenes, 1x2 grid
    valid = np.array([[[True, True]], [[True, True]], [[True, False]]])
    median, count = median_composite(stack, valid, min_observations=3)
    assert median[0, 0] == 3.0                                           # median of 1, 5, 3
    assert np.isnan(median[0, 1])                                        # only 2 valid observations
    assert count.tolist() == [[3, 2]]
