"""Transfer test helpers. Arrays here are synthetic test fixtures, not data."""

import numpy as np
import pytest

from app.model.heat import HeatModel
from app.model.transfer import block_centres_m, inside_bounds, offset_adjusted


def test_block_centres_hand_checked():
    # A 2 x 3 block grid of 90 m blocks, window [1000, 5000, 1270, 5180].
    # Flat index 0 is row 0 col 0: centre (1045, 5135). Index 5 is row 1 col 2: centre (1225, 5045).
    e_m, n_m = block_centres_m(np.array([0, 5, 1]), (2, 3), (1000.0, 5000.0, 1270.0, 5180.0), 90.0)
    assert e_m.tolist() == [1045.0, 1225.0, 1135.0]
    assert n_m.tolist() == [5135.0, 5045.0, 5135.0]


def test_block_centres_refuse_swapped_bounds():
    with pytest.raises(ValueError):
        block_centres_m(np.array([0]), (1, 1), (1000.0, 5180.0, 1270.0, 5000.0), 90.0)


def test_inside_bounds_includes_edges():
    mask = inside_bounds(np.array([0.0, 10.0, 10.1, 5.0]), np.array([5.0, 10.0, 5.0, -0.1]), (0.0, 0.0, 10.0, 10.0))
    assert mask.tolist() == [True, True, False, False]


def test_offset_adjusted_shifts_only_the_base_temperature():
    model = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=6.0, k_built_c_per_fraction=-2.0, k_bare_c_per_fraction=2.0)
    canopy, built, bare = np.array([0.5, 0.0]), np.array([0.0, 1.0]), np.array([0.0, 0.0])
    # Predictions: 40 - 6*0.5 = 37.0, and 40 - 2 = 38.0. Observed 38.5 and 39.5: residuals +1.5 each, so +1.5.
    shifted = offset_adjusted(model, np.array([38.5, 39.5]), canopy, built, bare)
    assert shifted.t_base_c == pytest.approx(41.5)
    assert (shifted.k_canopy_c_per_fraction, shifted.k_built_c_per_fraction, shifted.k_bare_c_per_fraction) == (6.0, -2.0, 2.0)
    assert np.allclose(shifted.predict_c(canopy, built, bare), [38.5, 39.5])
