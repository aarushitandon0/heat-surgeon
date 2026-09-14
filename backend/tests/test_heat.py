"""Baseline heat model prediction and least-squares recovery, against hand-checked values.

Arrays here are synthetic test fixtures, not data.
"""

import numpy as np
import pytest

from app.model.heat import HeatModel, contrasts, fit, reference_view


def test_contrasts_and_reference_view_hand_checked():
    # Paved reference: canopy -3, built +2, paved 0, bare +1 (relative to paved).
    model = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=3.0, k_built_c_per_fraction=2.0, k_bare_c_per_fraction=1.0)
    # Independent coefficient variances 0.25 (t), 1 (k_canopy), 4 (k_built), 9 (k_bare); no covariances.
    covariance = np.diag([0.25, 1.0, 4.0, 9.0])
    pairs = {(a, b): (d, se) for a, b, d, se in contrasts(model, covariance)}
    # canopy - built = -3 - 2 = -5; var = 1 + 4 = 5
    assert np.isclose(pairs[("canopy", "built")][0], -5.0) and np.isclose(pairs[("canopy", "built")][1], np.sqrt(5))
    # built - paved = 2; var = 4 (paved has no variance of its own)
    assert np.allclose(pairs[("built", "paved")], (2.0, 2.0))
    # built - bare = 1; var = 4 + 9 = 13
    assert np.allclose(pairs[("built", "bare")], (1.0, np.sqrt(13)))
    view = reference_view(model, covariance, "bare")
    # fully bare cell = 40 + 1 = 41, var = 0.25 + 9; paved - bare = -1, var 9; built - bare = 1, var 13
    assert np.allclose(view["t_reference_c"], (41.0, np.sqrt(9.25)))
    assert np.allclose(view["paved"], (-1.0, 3.0))
    assert np.allclose(view["built"], (1.0, np.sqrt(13)))
    assert "bare" not in view


def test_prediction_hand_checked():
    # 40 - 3 * 0.5 + 2 * 0.2 + 1 * 0.1 = 40 - 1.5 + 0.4 + 0.1 = 39.0
    model = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=3.0, k_built_c_per_fraction=2.0, k_bare_c_per_fraction=1.0)
    assert np.isclose(model.predict_c(0.5, 0.2, 0.1), 39.0)


def test_fit_recovers_known_coefficients_from_noiseless_data():
    rng = np.random.default_rng(0)
    parts = rng.dirichlet([1, 1, 1, 1], size=300)  # canopy, built, paved, bare fractions summing to one
    canopy, built, bare = parts[:, 0], parts[:, 1], parts[:, 3]
    truth = HeatModel(40.0, 3.0, 2.0, 1.0)
    model, standard_errors, _ = fit(truth.predict_c(canopy, built, bare), canopy, built, bare)
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
