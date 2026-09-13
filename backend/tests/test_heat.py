"""Baseline heat model prediction and least-squares recovery, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest

from app.model.heat import HeatModel, fit


def test_prediction_hand_checked():
    # 40 - 3 * 0.5 + 2 * 0.2 + 1 * 0.1 = 40 - 1.5 + 0.4 + 0.1 = 39.0
    model = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=3.0, k_built_c_per_fraction=2.0, k_bare_c_per_fraction=1.0)
    assert np.isclose(model.predict_c(0.5, 0.2, 0.1), 39.0)


def test_fit_recovers_known_coefficients_from_noiseless_data():
    rng = np.random.default_rng(0)
    parts = rng.dirichlet([1, 1, 1, 1], size=300)  # canopy, built, paved, bare fractions summing to one
    canopy, built, bare = parts[:, 0], parts[:, 1], parts[:, 3]
    truth = HeatModel(40.0, 3.0, 2.0, 1.0)
    model, standard_errors = fit(truth.predict_c(canopy, built, bare), canopy, built, bare)
    assert np.isclose(model.t_base_c, 40.0)
    assert np.isclose(model.k_canopy_c_per_fraction, 3.0)
    assert np.isclose(model.k_built_c_per_fraction, 2.0)
    assert np.isclose(model.k_bare_c_per_fraction, 1.0)
    assert np.allclose(standard_errors, 0, atol=1e-8)


def test_fit_refuses_unidentifiable_coefficients():
    # No paved surface anywhere: canopy + built + bare = 1 is collinear with the intercept.
    canopy = np.linspace(0, 0.5, 50)
    built = np.linspace(0.5, 0.2, 50) ** 2
    with pytest.raises(ValueError, match="not identifiable"):
        fit(np.full(50, 40.0), canopy, built, 1 - canopy - built)
