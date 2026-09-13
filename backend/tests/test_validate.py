"""Hold-out error metrics and the split, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest

from app.model.validate import holdout_split, r2_score, rmse_c


def test_rmse_hand_checked():
    # errors 0 and 2: sqrt((0 + 4) / 2) = sqrt(2)
    assert np.isclose(rmse_c([1.0, 2.0], [1.0, 4.0]), np.sqrt(2))


def test_r2_hand_checked():
    # observed 1, 2, 3 (mean 2): SS_tot = 1 + 0 + 1 = 2; predicted 1, 2, 4: SS_res = 1; R2 = 1 - 1/2
    assert np.isclose(r2_score([1.0, 2.0, 3.0], [1.0, 2.0, 4.0]), 0.5)


def test_holdout_split_is_disjoint_complete_sized_and_deterministic():
    fit_a, hold_a = holdout_split(10, 0.2, seed=42)
    fit_b, hold_b = holdout_split(10, 0.2, seed=42)
    assert len(hold_a) == 2 and len(fit_a) == 8
    assert set(fit_a).isdisjoint(hold_a)
    assert sorted(set(fit_a) | set(hold_a)) == list(range(10))
    assert np.array_equal(hold_a, hold_b)


def test_holdout_split_refuses_degenerate_sizes():
    with pytest.raises(ValueError):
        holdout_split(3, 0.1, seed=0)
