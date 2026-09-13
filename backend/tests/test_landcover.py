"""NDVI, OSM width rules, surface classification and block aggregation, against hand-checked values.

Arrays and OSM features here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest
from affine import Affine

from app import config
from app.data.landcover import (
    BARE,
    BUILT,
    CANOPY,
    CARRIAGEWAY,
    FOOTWAY,
    LandCoverError,
    block_fractions,
    block_mean,
    classify_surfaces,
    ndvi,
    ndvi_on_subgrid,
    way_width_m,
)


def test_ndvi_hand_checked():
    # (0.3 - 0.1) / (0.3 + 0.1) = 0.5
    assert np.isclose(ndvi(np.array([0.1]), np.array([0.3]), boa_add_offset_applied=True)[0], 0.5)


def test_ndvi_refuses_reflectance_without_confirmed_offset():
    with pytest.raises(LandCoverError, match="BOA_ADD_OFFSET"):
        ndvi(np.array([0.1]), np.array([0.3]), boa_add_offset_applied=False)


def test_way_width_rules():
    assert way_width_m({"highway": "primary", "width": "18 m"}) == (18.0, "carriageway")
    assert way_width_m({"highway": "primary", "lanes": "2"}) == (2 * config.LANE_WIDTH_M, "carriageway")
    assert way_width_m({"highway": "residential"}) == (config.DEFAULT_CARRIAGEWAY_WIDTH_M["residential"], "carriageway")
    assert way_width_m({"highway": "footway", "footway": "sidewalk"}) == (config.SIDEWALK_WIDTH_M, "footway")
    assert way_width_m({"highway": "footway", "footway": "crossing"}) is None
    assert way_width_m({"highway": "platform"}) is None


def test_ndvi_replicates_onto_offset_subgrid_exactly():
    # 10 m grid from e=0, n=20; 1 m sub-grid starting 5 m in: first sub-pixel sits in fine pixel (0, 0),
    # sub-pixel 5 crosses into fine column 1.
    values = np.array([[0.1, 0.9], [0.3, 0.7]])
    fine = ndvi_on_subgrid(values, (10.0, 0, 0.0, 0, -10.0, 20.0), Affine(1, 0, 5.0, 0, -1, 15.0), (10, 10))
    assert fine[0, 0] == 0.1 and fine[0, 5] == 0.9 and fine[5, 0] == 0.3 and fine[9, 9] == 0.7


def test_classification_priority_and_block_fractions():
    # 20 m x 20 m window, 10 m NDVI: top-left pixel vegetated, the rest not.
    red = np.array([[0.05, 0.2], [0.2, 0.2]])
    nir = np.array([[0.45, 0.25], [0.25, 0.25]])        # NDVI 0.8, then about 0.11
    s2 = (10.0, 0, 0.0, 0, -10.0, 20.0)
    building = [[0, 20], [10, 20], [10, 10], [0, 10], [0, 20]]         # top-left 10 m square, under the canopy
    road = {"id": "r", "tags": {"highway": "residential", "width": "4"}, "coords": [[0, 5], [20, 5]]}
    osm = {"buildings": [{"id": "b", "tags": {}, "rings": [building]}], "highways": [road]}
    classes, _ = classify_surfaces(red, nir, s2, True, osm, (0.0, 0.0, 20.0, 20.0))
    assert classes[2, 2] == CANOPY                        # canopy wins over the building beneath it
    assert classes[5, 15] == BARE
    assert classes[15, 15] == CARRIAGEWAY                 # road centreline at n=5, 4 m wide
    cover = block_fractions(classes, 20)
    # canopy 100 of 400; road band n=3..7 is 4 m x 20 m = 80 sub-pixels (none under canopy); bare the rest
    assert np.isclose(cover.canopy_fraction[0, 0], 100 / 400)
    assert np.isclose(cover.paved_fraction[0, 0], 80 / 400)
    assert np.isclose(cover.bare_fraction[0, 0], 220 / 400)
    assert cover.built_fraction[0, 0] == 0.0


def test_block_mean_drops_partial_blocks():
    values = np.arange(16, dtype=float).reshape(4, 4)
    # 3x3 blocks of a 4x4 grid: one block, rows 0-2 and cols 0-2; mean of 0,1,2,4,5,6,8,9,10 = 5
    assert block_mean(values, 3).tolist() == [[5.0]]
