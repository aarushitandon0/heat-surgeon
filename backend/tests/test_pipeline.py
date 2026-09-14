"""Pipeline helpers against hand-checked values. Tags here are synthetic test fixtures, not data."""

import pytest

from app import config
from app.contracts import OptimizeRequest
from app.pipeline import UnpricedBudget, budget_for, building_height

BASE = {"generations": 1, "population": 2, "cost_weight_c_per_inr": 0.0}


def test_building_height_from_tags_hand_checked():
    assert building_height({"height": "12 m"}, 500.0) == (12.0, "osm_tag")
    # 4 levels x 3 m storey
    assert building_height({"building:levels": "4"}, 50.0) == (4 * config.STOREY_HEIGHT_M, "osm_tag")


def test_untagged_building_height_is_estimated_from_footprint_area():
    # Table: < 100 m2 -> 2 storeys, < 300 -> 3, < 1000 -> 4, else 5; 3 m a storey.
    assert building_height({}, 60.0) == (6.0, "estimated_from_area")
    assert building_height({}, 100.0) == (9.0, "estimated_from_area")
    assert building_height({}, 999.0) == (12.0, "estimated_from_area")
    assert building_height({}, 9674.0) == (15.0, "estimated_from_area")
    assert building_height({}, 0.0) == (config.DEFAULT_BUILDING_HEIGHT_M, "default_assumption")


def test_zero_height_or_levels_tags_are_treated_as_missing():
    assert building_height({"height": "0"}, 60.0) == (6.0, "estimated_from_area")
    assert building_height({"height": "0", "building:levels": "2"}, 60.0) == (2 * config.STOREY_HEIGHT_M, "osm_tag")
    assert building_height({"building:levels": "0"}, 500.0) == (12.0, "estimated_from_area")


def test_rupee_budget_caps_trees_at_the_high_end_of_the_cost_range():
    # 50,000 / 5,902 per tree (high end) = 8.47 -> 8 trees
    budget = budget_for(OptimizeRequest(trees_max=20, reflective_cells_max=0, budget_inr_max=50000, **BASE))
    assert budget.trees == 8


def test_rupee_budget_with_unpriced_coating_is_refused():
    with pytest.raises(UnpricedBudget, match="reflective_pavement"):
        budget_for(OptimizeRequest(trees_max=20, reflective_cells_max=10, budget_inr_max=50000, **BASE))
