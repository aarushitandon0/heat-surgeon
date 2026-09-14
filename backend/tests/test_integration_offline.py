"""Full pipeline from committed fixtures with the network disabled, for every fixture street.

Any attempt to open a non-loopback socket fails the test, so a hidden network call cannot pass silently.
The GA runs few generations here to keep the suite fast; the pipeline and contracts are the same.
"""

import socket

import pytest
from fastapi.testclient import TestClient

from app import config, jobs
from app.contracts import CalibrationResult, OptimizationResult, OptimizeJobHandle, StreetGeometry, StreetSummary, ThermalGrid
from app.main import app
from app.pipeline import street_ids

STREETS = street_ids()
REQUEST = {"trees_max": 12, "reflective_cells_max": 60, "generations": 6, "population": 16,
           "cost_weight_c_per_inr": 0.0, "run_baselines": True, "seed": 1}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"network access attempted: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(config, "USE_LIVE_DATA", False)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_there_are_four_fixture_streets_with_distinct_profiles():
    assert len(STREETS) == 4
    profiles = {StreetSummary(**s).profile for s in TestClient(app).get("/api/streets").json()}
    assert profiles == {"dense_commercial", "leafy_residential", "wide_arterial", "mixed"}


@pytest.mark.parametrize("street_id", STREETS)
def test_full_pipeline_offline(client, street_id):
    summaries = {s["id"]: s for s in client.get("/api/streets").json()}
    assert summaries[street_id]["cached"] is True

    thermal = ThermalGrid(**client.get(f"/api/street/{street_id}/thermal", params={"scope": "window"}).json())
    assert thermal.stats.valid_pixels > 0 and thermal.provenance.scene_count > 0
    ThermalGrid(**client.get(f"/api/street/{street_id}/thermal", params={"scope": "street"}).json())

    geometry = StreetGeometry(**client.get(f"/api/street/{street_id}/geometry").json())
    assert geometry.cross_section.bands and geometry.buildings

    calibration = CalibrationResult(**client.post(f"/api/street/{street_id}/calibrate", json={}).json())
    assert calibration.rmse_holdout_c < calibration.rmse_mean_baseline_c
    assert len(calibration.contrasts) == 6

    response = client.post(f"/api/street/{street_id}/optimize", json=REQUEST)
    assert response.status_code == 200, response.text
    handle = OptimizeJobHandle(**response.json())

    types = []
    with client.websocket_connect(handle.ws_url) as ws:
        while True:
            message = ws.receive_json()
            types.append(message["type"])
            if message["type"] in ("done", "error"):
                break
    assert types[-1] == "done", jobs.JOBS[handle.job_id].messages[-1]
    assert "progress" in types

    result = OptimizationResult(**client.get(f"/api/job/{handle.job_id}/result").json())
    arms = result.comparison
    for a in (arms.random, arms.greedy, arms.design_guideline, arms.ga):
        assert a.trees <= REQUEST["trees_max"] and a.reflective_cells <= REQUEST["reflective_cells_max"]
    assert result.resolution.output_kind == "model_output_at_design_resolution"
    assert result.resolution.measurement_resolution_m == 30 and result.resolution.design_resolution_m == 2
    assert {p.product for p in result.provenance} == {"surface_temperature", "land_cover"}
    if result.unpriced_interventions:
        assert result.cost_inr_low is None
    assert result.temp_delta_c_high <= 0


def test_unknown_street_is_404_and_unpriced_rupee_budget_is_422(client):
    assert client.get("/api/street/not-a-street/geometry").status_code == 404
    body = {**REQUEST, "budget_inr_max": 100000}
    assert client.post(f"/api/street/{STREETS[0]}/optimize", json=body).status_code == 422
