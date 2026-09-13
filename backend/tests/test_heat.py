"""Heat model prediction and least-squares recovery, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest

from app.model.heat import HeatModel, fit


def test_prediction_hand_checked():
    # 40 - 5 * 0.2 - 20 * (0.19 - 0.14) + 3 * 0.5 = 40 - 1.0 - 1.0 + 1.5 = 39.5
    model = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=5.0, k_albedo_c_per_unit_albedo=20.0,
                      k_impervious_c_per_fraction=3.0, albedo_reference=0.14)
    assert np.isclose(model.predict_c(0.2, 0.19, 0.5), 39.5)


def test_fit_recovers_known_coefficients_from_noiseless_data():
    rng = np.random.default_rng(0)
    canopy, impervious, albedo = rng.uniform(0, 1, 200), rng.uniform(0, 1, 200), rng.uniform(0.05, 0.25, 200)
    truth = HeatModel(40.0, 5.0, 20.0, 3.0, albedo_reference=float(albedo.mean()))
    model, standard_errors = fit(truth.predict_c(canopy, albedo, impervious), canopy, albedo, impervious)
    assert np.isclose(model.t_base_c, 40.0)
    assert np.isclose(model.k_canopy_c_per_fraction, 5.0)
    assert np.isclose(model.k_albedo_c_per_unit_albedo, 20.0)
    assert np.isclose(model.k_impervious_c_per_fraction, 3.0)
    assert np.allclose(standard_errors, 0, atol=1e-8)


def test_fit_refuses_unidentifiable_coefficients():
    # Constant albedo makes the delta-albedo column all zeros, so k_albedo cannot be identified.
    canopy, impervious = np.linspace(0, 1, 50), np.linspace(1, 0, 50) ** 2
    with pytest.raises(ValueError, match="not identifiable"):
        fit(np.full(50, 40.0), canopy, np.full(50, 0.14), impervious)
