"""Layout cost ranges against hand-checked values from the cited schedule rates."""

import pytest

from app import config
from app.model.cost import layout_cost_inr, unit_cost_inr, unpriced


def test_tree_unit_cost_is_planting_plus_guard_range():
    # RUIDP ISOR 2023: 1,682 planting with first-year care + guard 2,038 (low) or 4,220 (high)
    assert unit_cost_inr("tree") == (3720.0, 5902.0)


def test_layout_cost_hand_checked():
    # 20 trees: 20 * 3,720 = 74,400 to 20 * 5,902 = 118,040
    assert layout_cost_inr({"tree": 20, "reflective_pavement": 0}) == (74400.0, 118040.0)


def test_layout_with_an_unpriced_intervention_has_no_cost():
    counts = {"tree": 20, "reflective_pavement": 150}
    assert unpriced(counts) == ["reflective_pavement"]
    assert layout_cost_inr(counts) is None


def test_every_intervention_type_has_an_explicit_cost_entry():
    from typing import get_args

    from app.contracts import InterventionType
    assert set(config.COST_INR_BY_INTERVENTION) == set(get_args(InterventionType))


def test_unknown_intervention_type_raises():
    with pytest.raises(KeyError):
        unit_cost_inr("fountain")
