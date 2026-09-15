"""Record a replayable snapshot of real API responses for every fixture street.

The frontend replays these files when the backend cannot be reached, and says so on screen. Every file is a
response from this API, recorded in-process from committed fixtures with live data switched off: nothing is
edited, summarised or synthesised. Optimizer progress messages keep the time they arrived, so a replay runs at
the recorded pace.

    python -m app.snapshot                      # all fixture streets, the default request as a short search
    python -m app.snapshot --street pune-fc-road
"""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.contracts import OptimizeRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "frontend" / "public" / "snapshot"
SNAPSHOT_FORMAT_VERSION = 1

# Mirrors DEFAULT_REQUEST in frontend/src/lib/search.ts: the request the app opens on.
DEFAULT_REQUEST = OptimizeRequest(trees_max=20, reflective_cells_max=0, budget_inr_max=None, generations=400,
                                  population=120, cost_weight_c_per_inr=0.0, run_baselines=True, seed=42)
# What the snapshot records: the default request at the short search length (SEARCH_LENGTHS.short in
# frontend/src/lib/search.ts). A replay runs at the recorded pace, and a full search recorded at 4-5 minutes per
# street is too long to watch. At this budget and seed the short search reaches the same layout value
# (docs/methodology.md, "Demo safety kit"); the replay shows its settings and generation total.
RECORDED_REQUEST = DEFAULT_REQUEST.model_copy(update={"generations": 150})
# Mirrors the calibration request the store sends in selectStreet.
CALIBRATION_REQUEST = {"holdout_fraction": 0.2, "seed": 42}


def _write(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _ok(response):
    if response.status_code != 200:
        raise RuntimeError(f"{response.request.method} {response.request.url} answered {response.status_code}: {response.text}")
    return response.json()


def _git_commit() -> str | None:
    """The commit the recording was made from, with "-dirty" when tracked files had uncommitted changes."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    try:
        commit = git("rev-parse", "--short", "HEAD")
        return f"{commit}-dirty" if git("status", "--porcelain", "--untracked-files=no") else commit
    except (OSError, subprocess.CalledProcessError):
        return None


def record_street(client: TestClient, street_id: str, request: OptimizeRequest) -> dict:
    """Write one street's responses under SNAPSHOT_DIR/<street_id>/ and return its manifest entry."""
    out = SNAPSHOT_DIR / street_id
    size_bytes = 0
    size_bytes += _write(out / "geometry.json", _ok(client.get(f"/api/street/{street_id}/geometry")))
    size_bytes += _write(out / "basemap.json", _ok(client.get(f"/api/street/{street_id}/basemap")))
    for scope in ("window", "street"):
        size_bytes += _write(out / f"thermal-{scope}.json",
                             _ok(client.get(f"/api/street/{street_id}/thermal", params={"scope": scope})))
    size_bytes += _write(out / "calibration.json", _ok(client.post(f"/api/street/{street_id}/calibrate", json=CALIBRATION_REQUEST)))

    started = time.monotonic()
    handle = _ok(client.post(f"/api/street/{street_id}/optimize", json=request.model_dump()))
    size_bytes += _write(out / "optimize-handle.json", handle)

    stream = []
    with client.websocket_connect(handle["ws_url"]) as ws:
        while True:
            message = ws.receive_json()
            stream.append({"elapsed_s": round(time.monotonic() - started, 3), "message": message})
            if message["type"] in ("done", "error"):
                break
    if stream[-1]["message"]["type"] != "done":
        raise RuntimeError(f"{street_id}: the search ended with {stream[-1]['message']}")
    size_bytes += _write(out / "stream.json", stream)
    size_bytes += _write(out / "result.json", _ok(client.get(f"/api/job/{handle['job_id']}/result")))

    search_s = stream[-1]["elapsed_s"]
    print(f"{street_id}: {len(stream)} messages over {search_s:.1f} s, {size_bytes / 1e6:.2f} MB", flush=True)
    return {"id": street_id, "search_s": search_s, "messages": len(stream), "size_bytes": size_bytes}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--street", action="append", help="street id; repeat for several (default: every fixture street)")
    parser.add_argument("--ranking-only", action="store_true",
                        help="record only /api/ranking into ranking.json; street recordings and manifest stay as they are")
    args = parser.parse_args(argv)

    config.USE_LIVE_DATA = False   # a snapshot is a recording of the offline path, never of a network call
    from app.main import app
    from app.pipeline import street_ids

    client = TestClient(app)
    if args.ranking_only:
        # ranking.json carries its own generated_at and git_commit, so the street manifest is not rewritten.
        size_bytes = _write(SNAPSHOT_DIR / "ranking.json", _ok(client.get("/api/ranking")))
        print(f"recorded ranking.json, {size_bytes / 1e6:.2f} MB", flush=True)
        return
    summaries = _ok(client.get("/api/streets"))
    wanted = args.street or street_ids()
    recorded = [record_street(client, street_id, RECORDED_REQUEST) for street_id in wanted]

    manifest_path = SNAPSHOT_DIR / "manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"streets": []}
    by_id = {s["id"]: s for s in previous.get("streets", [])} | {s["id"]: s for s in recorded}
    _write(SNAPSHOT_DIR / "streets.json", summaries)
    ranking_response = client.get("/api/ranking")
    if ranking_response.status_code == 200:
        _write(SNAPSHOT_DIR / "ranking.json", ranking_response.json())
    else:
        print(f"no street ranking recorded: {ranking_response.json().get('detail')}", flush=True)
    _write(manifest_path, {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "source_adapter": config.ACTIVE_SOURCE_ADAPTER,
        "calibration_request": CALIBRATION_REQUEST,
        "optimize_request": RECORDED_REQUEST.model_dump(),
        "streets": [by_id[s["id"]] for s in summaries if s["id"] in by_id],
    })


if __name__ == "__main__":
    main()
