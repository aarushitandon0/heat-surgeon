"""Storeys-by-area derivation against hand-checked values. Tags and rings here are synthetic test fixtures."""

from app import config
from app.data.heights import parse_levels, storeys_by_area, tagged_samples


def test_parse_levels_accepts_only_positive_whole_numbers():
    assert parse_levels("3") == 3
    assert parse_levels("4.0") == 4
    assert parse_levels("0") is None
    assert parse_levels("2.5") is None
    assert parse_levels("Ground+3") is None
    assert parse_levels(None) is None


def test_storeys_by_area_takes_the_median_per_bin():
    samples = [(50, 1), (60, 3), (80, 2), (150, 3), (200, 5), (2000, 6)]
    # < 100: [1, 3, 2] -> 2; 100 to 300: [3, 5] -> 4; >= 300: [6] -> 6. An area on a bound goes up a bin.
    assert storeys_by_area(samples + [(100, 5)], (100.0, 300.0)) == [
        {"upper_bound_m2": 100.0, "median_levels": 2, "count": 3},
        {"upper_bound_m2": 300.0, "median_levels": 5, "count": 3},
        {"upper_bound_m2": float("inf"), "median_levels": 6, "count": 1},
    ]


def test_tagged_samples_uses_footprint_area_and_skips_untagged():
    square_10m = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    buildings = [
        {"id": "way/1", "tags": {"building:levels": "4"}, "rings": [square_10m]},
        {"id": "way/2", "tags": {"building": "yes"}, "rings": [square_10m]},
    ]
    assert tagged_samples(buildings) == {"way/1": (100.0, 4)}


def test_frozen_table_matches_its_bin_bounds():
    bounds = tuple(bound for bound, _ in config.BUILDING_STOREYS_BY_FOOTPRINT_AREA_M2[:-1])
    assert bounds == config.BUILDING_AREA_BIN_UPPER_BOUNDS_M2
