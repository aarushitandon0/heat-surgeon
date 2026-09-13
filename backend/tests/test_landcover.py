"""NDVI and exact-overlap land cover fractions, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest

from app.data.landcover import LandCoverError, aggregate_fraction, ndvi


def test_ndvi_hand_checked():
    # (0.3 - 0.1) / (0.3 + 0.1) = 0.5
    assert np.isclose(ndvi(np.array([0.1]), np.array([0.3]), boa_add_offset_applied=True)[0], 0.5)


def test_ndvi_refuses_reflectance_without_confirmed_offset():
    with pytest.raises(LandCoverError, match="BOA_ADD_OFFSET"):
        ndvi(np.array([0.1]), np.array([0.3]), boa_add_offset_applied=False)


def test_offset_grid_aggregation_uses_exact_area_overlap():
    # 10 m grid from e=0; one 30 m cell from e=5 to 35 (and n offset by 5 m the same way).
    # It covers half of fine columns 0 and 3 and all of 1 and 2: weights 0.5, 1, 1, 0.5 (sum 3).
    # Indicator true in columns 0 and 3 only: (0.5 + 0.5) / 3 = 1/3 in every row, so 1/3 overall.
    indicator = np.tile(np.array([True, False, False, True]), (4, 1))
    valid = np.ones((4, 4), dtype=bool)
    fine = (10.0, 0.0, 0.0, 0.0, -10.0, 40.0)
    coarse = (30.0, 0.0, 5.0, 0.0, -30.0, 35.0)
    fraction, valid_fraction = aggregate_fraction(indicator, valid, fine, coarse, (1, 1))
    assert np.isclose(fraction[0, 0], 1 / 3)
    assert valid_fraction[0, 0] == 1.0


def test_aggregation_counts_only_observed_area():
    # Aligned grids, 30 m cell = 3x3 fine pixels. 3 unobserved, 2 of the 6 observed are canopy.
    indicator = np.array([[True, True, False], [False, False, False], [True, True, True]])
    valid = np.array([[True, True, True], [True, True, True], [False, False, False]])
    grid = (10.0, 0.0, 0.0, 0.0, -10.0, 30.0)
    fraction, valid_fraction = aggregate_fraction(indicator, valid, grid, (30.0, 0.0, 0.0, 0.0, -30.0, 30.0), (1, 1))
    assert np.isclose(fraction[0, 0], 2 / 6)
    assert np.isclose(valid_fraction[0, 0], 6 / 9)


def test_aggregation_refuses_grids_that_do_not_cover():
    grid = (10.0, 0.0, 0.0, 0.0, -10.0, 30.0)
    with pytest.raises(LandCoverError):
        aggregate_fraction(np.ones((3, 3), bool), np.ones((3, 3), bool), grid,
                           (30.0, 0.0, -5.0, 0.0, -30.0, 30.0), (1, 1))
