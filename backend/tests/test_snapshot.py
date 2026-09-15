"""The snapshot recorder writes every file the frontend replay reads (frontend/src/lib/replay.ts, SnapshotFile)."""

import json

from fastapi.testclient import TestClient

from app import config, snapshot
from app.contracts import CalibrationResult, OptimizationResult, OptimizeJobHandle, OptimizeRequest
from app.main import app
from app.pipeline import street_ids

REPLAY_FILES = {"geometry", "basemap", "thermal-window", "thermal-street", "calibration", "optimize-handle", "stream", "result"}
TINY = OptimizeRequest(trees_max=6, reflective_cells_max=0, budget_inr_max=None, generations=3, population=8,
                       cost_weight_c_per_inr=0.0, run_baselines=True, seed=1)


def test_record_street_writes_every_replay_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USE_LIVE_DATA", False)
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path)
    street_id = street_ids()[0]

    entry = snapshot.record_street(TestClient(app), street_id, TINY)

    written = {p.stem for p in (tmp_path / street_id).glob("*.json")}
    assert written == REPLAY_FILES
    read = lambda name: json.loads((tmp_path / street_id / f"{name}.json").read_text(encoding="utf-8"))
    CalibrationResult(**read("calibration"))
    OptimizeJobHandle(**read("optimize-handle"))
    result = OptimizationResult(**read("result"))
    assert result.street.id == street_id

    stream = read("stream")
    assert stream[-1]["message"]["type"] == "done"
    assert any(e["message"]["type"] == "progress" for e in stream)
    elapsed_s = [e["elapsed_s"] for e in stream]
    assert elapsed_s == sorted(elapsed_s) and elapsed_s[0] >= 0
    assert entry["id"] == street_id and entry["messages"] == len(stream) and entry["search_s"] == elapsed_s[-1]


def test_default_request_mirrors_the_frontend_default():
    # frontend/src/lib/search.ts DEFAULT_REQUEST
    assert snapshot.DEFAULT_REQUEST.model_dump() == {
        "trees_max": 20, "reflective_cells_max": 0, "budget_inr_max": None, "generations": 400, "population": 120,
        "cost_weight_c_per_inr": 0.0, "run_baselines": True, "seed": 42,
    }


def test_recorded_request_is_the_default_at_the_short_search_length():
    # frontend/src/lib/search.ts SEARCH_LENGTHS.short = { generations: 150, population: 120 }
    assert snapshot.RECORDED_REQUEST.model_dump() == {**snapshot.DEFAULT_REQUEST.model_dump(), "generations": 150}
