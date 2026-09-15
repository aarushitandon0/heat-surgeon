"""Street ranking helpers and contract checks. Values here are synthetic test fixtures, not data."""

import numpy as np
import pytest
from pydantic import ValidationError

from app.contracts import RankedStreet
from app.ranking import (
    calibrated_bounds_m,
    cooling_gradient,
    cooling_per_lakh_inr,
    design_corners_m,
    difference_significant,
    edge_margin_m,
    rank_intervals,
    ranked,
)


def test_calibrated_bounds_drop_the_trailing_partial_block_hand_checked():
    # FC Road's window [376755, 2047155, 378765, 2049165]: 67 cells of 30 m = 2,010 m. 67 // 3 = 22 blocks of 90 m
    # = 1,980 m from the north-west corner, so the south edge rises 30 m and the east edge moves in 30 m.
    bounds_m = calibrated_bounds_m((376755.0, 2047155.0, 378765.0, 2049165.0), 67, 3, 30.0)
    assert bounds_m == (376755.0, 2047185.0, 378735.0, 2049165.0)
    # A window of whole blocks is unchanged.
    assert calibrated_bounds_m((0.0, 0.0, 180.0, 180.0), 6, 3, 30.0) == (0.0, 0.0, 180.0, 180.0)


def test_cooling_per_lakh_inr_hand_checked():
    # 0.70 °C for ₹74,400 to ₹1,18,040: 0.70 / 118040 * 100000 = 0.593020, and 0.70 / 74400 * 100000 = 0.940860.
    low, high = cooling_per_lakh_inr(-0.70, 74_400, 118_040)
    assert low == pytest.approx(0.593019315, abs=1e-8)
    assert high == pytest.approx(0.940860215, abs=1e-8)


@pytest.mark.parametrize("delta_c, low, high", [(0.0, 1.0, 2.0), (0.1, 1.0, 2.0), (-0.5, 0.0, 2.0), (-0.5, 3.0, 2.0)])
def test_cooling_per_lakh_inr_refuses_no_cooling_and_bad_costs(delta_c, low, high):
    with pytest.raises(ValueError):
        cooling_per_lakh_inr(delta_c, low, high)


def test_cooling_gradient_hand_checked_and_reproduces_the_change():
    # 10 crown cells over paving, 4 over bare ground, 2 over roofs, 2,000 design cells.
    gradient = cooling_gradient(10, 4, 2, 2000)
    assert gradient.tolist() == pytest.approx([-0.008, -0.001, -0.002])
    # FC Road's coefficients: k_canopy 5.68, k_built -2.15, k_bare 2.29.
    # Change = -(10 * 5.68 + 4 * (5.68 + 2.29) + 2 * (5.68 - 2.15)) / 2000 = -(56.8 + 31.88 + 7.06) / 2000 = -0.04787.
    assert gradient @ np.array([5.68, -2.15, 2.29]) == pytest.approx(-0.04787)


def test_difference_significant_hand_checked():
    covariance = np.diag([0.01, 0.0, 0.0])
    g_a, g_b = np.array([1.0, 0.0, 0.0]), np.array([0.5, 0.0, 0.0])
    # Same window: difference gradient [0.5, 0, 0], variance 0.25 * 0.01 = 0.0025, sd 0.05, threshold 1.96 * 0.05 = 0.098.
    assert not difference_significant(0.05, g_a, covariance, 0.03, g_b, covariance, True, 1.96)
    assert difference_significant(0.20, g_a, covariance, 0.05, g_b, covariance, True, 1.96)
    # Different windows: variance 1 * 0.01 + 0.25 * 0.01 = 0.0125, sd 0.1118, threshold 0.2191.
    assert not difference_significant(0.20, g_a, covariance, 0.05, g_b, covariance, False, 1.96)
    assert difference_significant(0.30, g_a, covariance, 0.05, g_b, covariance, False, 1.96)
    # Same window with identical gradients: the shared coefficient error cancels, so any difference is real.
    assert difference_significant(0.051, g_a, covariance, 0.050, g_a, covariance, True, 1.96)


def test_rank_intervals_hand_checked():
    covariance = {"w": np.diag([0.01, 0.0, 0.0]), "v": np.diag([0.01, 0.0, 0.0])}
    gradient = np.array([1.0, 0.0, 0.0])
    # Across windows each pair's threshold is 1.96 * sqrt(0.02) = 0.2772.
    # Values 1.0 (w), 0.9 (v), 0.5 (w): 1.0 vs 0.9 across windows ties; 1.0 vs 0.5 in one window, identical gradients,
    # differs; 0.9 vs 0.5 across windows differs by 0.4 > 0.2772.
    intervals = rank_intervals([1.0, 0.9, 0.5], [gradient, gradient, gradient], ["w", "v", "w"], covariance, 1.96)
    assert intervals == [(1, 2), (1, 2), (3, 3)]


def test_design_corners_and_edge_margin_hand_checked():
    # Street running north from (0, 0), grid 200 m long and 40 m across to the right (east).
    frame = {"origin": [0.0, 0.0], "along": [0.0, 1.0], "right": [1.0, 0.0]}
    corners_m = design_corners_m(frame, 200.0, 40.0)
    assert corners_m.tolist() == [[0.0, 0.0], [0.0, 200.0], [40.0, 200.0], [40.0, 0.0]]
    # Window [-10, -5, 100, 300]: west 10, east 60, south 5, north 100. Smallest is 5.
    assert edge_margin_m(corners_m, (-10.0, -5.0, 100.0, 300.0)) == 5.0
    # Shift the window so the south edge is above the grid's start: a corner lies 15 m outside.
    assert edge_margin_m(corners_m, (-10.0, 15.0, 100.0, 300.0)) == -15.0


def row(name: str, temp_delta_c: float, **overrides) -> dict:
    cost_low, cost_high = 74_400.0, 118_040.0
    low, high = cooling_per_lakh_inr(temp_delta_c, cost_low, cost_high)
    values = dict(osm_name=name, window_street_id="w", fixture_street_id=None, segment_wgs84=((73.8, 18.5), (73.81, 18.51)),
                  highway="residential", cross_section_source="published_design", tree_capacity=30, trees=20,
                  temp_delta_c=temp_delta_c, temp_delta_se_c=0.1, cooling_gradient=[-0.01, 0.0, 0.0],
                  random_temp_delta_c=-0.3, design_guideline_temp_delta_c=-0.3,
                  cost_inr_low=cost_low, cost_inr_high=cost_high,
                  cooling_c_per_lakh_inr_low=low, cooling_c_per_lakh_inr_high=high)
    return {**values, **overrides}


def test_ranked_orders_by_cooling_per_lakh_then_name_and_ties_equal_values():
    # Identical gradients in one window: B and A differ, A and C are equal, so A and C tie.
    covariance = {"w": np.diag([1.0, 0.0, 0.0])}
    streets = ranked([row("B Road", -0.5), row("A Road", -0.9), row("C Road", -0.9)], covariance, 1.96)
    assert [(s.rank, s.rank_best, s.rank_worst, s.osm_name) for s in streets] == [
        (1, 1, 2, "A Road"), (2, 1, 2, "C Road"), (3, 3, 3, "B Road")]


def contract_row(name: str, **overrides) -> dict:
    values = {k: v for k, v in row(name, -0.7).items() if k != "cooling_gradient"}
    return {**values, **overrides}


def test_ranked_street_refuses_more_trees_than_capacity_warming_and_rank_outside_its_range():
    with pytest.raises(ValidationError):
        RankedStreet(rank=1, rank_best=1, rank_worst=1, **contract_row("A", trees=31))
    with pytest.raises(ValidationError):
        RankedStreet(rank=1, rank_best=1, rank_worst=1, **contract_row("A", temp_delta_c=0.1))
    with pytest.raises(ValidationError):
        RankedStreet(rank=3, rank_best=1, rank_worst=2, **contract_row("A"))


def test_ranking_endpoint_is_404_with_the_command_when_never_computed(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    monkeypatch.setattr(config, "RANKING_PATH", tmp_path / "missing.json")
    response = TestClient(app).get("/api/ranking")
    assert response.status_code == 404
    assert "python -m app.ranking" in response.json()["detail"]
