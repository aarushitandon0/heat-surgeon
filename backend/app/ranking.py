"""Rank the streets inside the calibrated windows by modelled cooling per ₹1 lakh (docs/methodology.md, "Street ranking").

    python -m app.ranking [--workers 4]

Every named street in RANKING_HIGHWAY_CLASSES whose longest OSM way holds the 200 m design segment is ranked, in
the window where that segment sits farthest inside. Each street uses its own window's calibration: the transfer
test showed one calibration per 2 km window serves the streets inside it, and one model does not serve other
windows. Every street gets the same matched budget the app opens on (RANKING_TREES_MAX trees, trees only), a short
search, and the random and design-guideline baselines. Reads fixtures only; never touches the network.

Writes RANKING_PATH (backend/fixtures/ranking/four-windows.json), served by GET /api/ranking.
"""

import argparse
import math
import time
from datetime import datetime, timezone
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from rasterio.warp import transform as warp_transform

from app import config
from app.contracts import (
    CalibrationRequest,
    OptimizeRequest,
    RankedStreet,
    RankingWindow,
    Resolution,
    SkippedStreet,
    StreetRanking,
)

LAKH_INR = 100_000

RANKING_REQUEST = OptimizeRequest(trees_max=config.RANKING_TREES_MAX, reflective_cells_max=0, budget_inr_max=None,
                                  generations=config.RANKING_GENERATIONS, population=config.RANKING_POPULATION,
                                  cost_weight_c_per_inr=0.0, run_baselines=True, seed=config.RANKING_SEED)


def cooling_per_lakh_inr(temp_delta_c: float, cost_inr_low: float, cost_inr_high: float) -> tuple[float, float]:
    """(low, high) modelled cooling per ₹1,00,000. Low divides by the high cost, high by the low cost."""
    if temp_delta_c >= 0:
        raise ValueError(f"no modelled cooling: temp_delta_c is {temp_delta_c}")
    if not 0 < cost_inr_low <= cost_inr_high:
        raise ValueError(f"cost range must satisfy 0 < low <= high, got {cost_inr_low}, {cost_inr_high}")
    drop_c = -temp_delta_c
    return drop_c / cost_inr_high * LAKH_INR, drop_c / cost_inr_low * LAKH_INR


def cooling_gradient(n_paved: int, n_bare: int, n_built: int, n_cells: int) -> np.ndarray:
    """d temp_delta_c / d [k_canopy, k_built, k_bare] for a trees-only layout.

    A crown cell over paving changes by -k_canopy, over bare ground by -k_canopy - k_bare, over a roof by
    -k_canopy - k_built, and over existing canopy by nothing (model/delta.py); the change is the mean over every design
    cell. It is linear in the three coefficients and does not involve t_base_c, so this gradient is exact.
    """
    return -np.array([n_paved + n_bare + n_built, n_built, n_bare], dtype=float) / n_cells


def crown_class_counts(grid, genome) -> tuple[int, int, int]:
    """(paved, bare, built) design cells under the layout's crowns."""
    from app.data.landcover import BARE, BUILT, CARRIAGEWAY, FOOTWAY

    canopy = grid.canopy_from(genome)
    classes = grid.classes
    return (int((canopy & np.isin(classes, (CARRIAGEWAY, FOOTWAY))).sum()), int((canopy & (classes == BARE)).sum()),
            int((canopy & (classes == BUILT)).sum()))


def difference_significant(value_a: float, gradient_a: np.ndarray, covariance_a: np.ndarray, value_b: float,
                           gradient_b: np.ndarray, covariance_b: np.ndarray, same_window: bool, z: float) -> bool:
    """Whether two streets' values differ by more than z standard errors of the calibration coefficients.

    In one window both values come from the same fitted coefficients, so the error of the difference uses the difference
    of the gradients. Across windows the fits are independent, so the variances add.
    """
    if same_window:
        d = np.asarray(gradient_a) - np.asarray(gradient_b)
        variance = float(d @ covariance_a @ d)
    else:
        variance = float(gradient_a @ covariance_a @ gradient_a + gradient_b @ covariance_b @ gradient_b)
    return abs(value_a - value_b) > z * math.sqrt(max(variance, 0.0))


def rank_intervals(values: list[float], gradients: list[np.ndarray], windows: list[str], covariances: dict,
                   z: float) -> list[tuple[int, int]]:
    """(best, worst) rank per street. Higher values rank higher; a street is only ranked below another it differs from."""
    n = len(values)
    intervals = []
    for i in range(n):
        better = worse = 0
        for j in range(n):
            if i != j and difference_significant(values[i], gradients[i], covariances[windows[i]], values[j], gradients[j],
                                                 covariances[windows[j]], windows[i] == windows[j], z):
                if values[j] > values[i]:
                    better += 1
                else:
                    worse += 1
        intervals.append((1 + better, n - worse))
    return intervals


def design_corners_m(frame: dict, length_m: float, width_m: float) -> np.ndarray:
    """The four corners of the design grid, [easting, northing] in metres, from a segment frame."""
    origin, along, right = (np.asarray(frame[k], dtype=float) for k in ("origin", "along", "right"))
    return np.array([origin, origin + along * length_m, origin + along * length_m + right * width_m, origin + right * width_m])


def edge_margin_m(corners_m: np.ndarray, bounds_m: tuple[float, float, float, float]) -> float:
    """Smallest distance from any corner to the window edge; negative when a corner lies outside."""
    min_e_m, min_n_m, max_e_m, max_n_m = bounds_m
    e_m, n_m = corners_m[:, 0], corners_m[:, 1]
    return float(min((e_m - min_e_m).min(), (max_e_m - e_m).min(), (n_m - min_n_m).min(), (max_n_m - n_m).min()))


def calibrated_bounds_m(bounds_m: tuple[float, float, float, float], window_cells: int, block_cells: int,
                        cell_m: float) -> tuple[float, float, float, float]:
    """The part of a window covered by whole calibration blocks.

    Blocks are laid from the north-west corner and trailing partial blocks are dropped (landcover.block_mean), so a
    67-cell window at 3 cells per block has 22 blocks: 1,980 m of its 2,010 m, missing a 30 m strip on the south and
    east. A design cell there has no calibration cell to take its residual from.
    """
    min_e_m, _, _, max_n_m = bounds_m
    covered_m = (window_cells // block_cells) * block_cells * cell_m
    return (min_e_m, max_n_m - covered_m, min_e_m + covered_m, max_n_m)


def candidates(windows: dict) -> tuple[list[tuple[str, str]], list[SkippedStreet], int]:
    """([(osm_name, window_street_id)], skipped, count of names too short for a design segment).

    A name found in several overlapping windows is ranked once, in the window where its segment sits farthest inside.
    """
    from app.optimizer.encoding import segment_frame

    best: dict[str, tuple[str, float]] = {}
    outside: dict[str, str] = {}
    too_short: set[str] = set()
    for street_id, window in windows.items():
        names = {w["tags"]["name"] for w in window.osm["highways"]
                 if w["tags"].get("name") and w["tags"].get("highway") in config.RANKING_HIGHWAY_CLASSES}
        for name in sorted(names):
            try:
                frame = segment_frame(window, name)
            except ValueError:
                too_short.add(name)
                continue
            if frame["way"]["tags"].get("highway") not in config.RANKING_HIGHWAY_CLASSES:
                continue
            corners_m = design_corners_m(frame, config.DESIGN_SEGMENT_LENGTH_M, config.DESIGN_CORRIDOR_WIDTH_M)
            calibrated_m = calibrated_bounds_m(window.bbox.bounds, window.manifest["window"]["shape"][0],
                                               config.CALIBRATION_BLOCK_CELLS, config.LANDSAT_CELL_SIZE_M)
            margin_m = edge_margin_m(corners_m, calibrated_m)
            if margin_m < 0:
                outside.setdefault(name, street_id)
            elif name not in best or margin_m > best[name][1]:
                best[name] = (street_id, margin_m)
    skipped = [SkippedStreet(osm_name=name, window_street_id=street_id,
                             reason="The design grid extends past the window's calibration cells.")
               for name, street_id in sorted(outside.items()) if name not in best]
    tasks = sorted((name, street_id) for name, (street_id, _) in best.items())
    return tasks, skipped, len(too_short - set(best) - set(outside))


@lru_cache(maxsize=None)
def _window_context(street_id: str):
    """Window, calibration and 1 m classification, once per window per worker process."""
    from app.data.fixtures import load_window
    from app.model.validate import calibrate, calibration_cells, window_surfaces

    window = load_window(street_id)
    run = calibrate(street_id, CalibrationRequest())
    classes_1m, transform = window_surfaces(window)
    cover, lst_c, _ = calibration_cells(window, classes_1m)
    residual_c = lst_c - run.model.predict_c(cover.canopy_fraction, cover.built_fraction, cover.bare_fraction)
    return window, run, classes_1m, transform, residual_c


def _rank_one(task: tuple[str, str]) -> dict:
    from app import pipeline
    from app.optimizer.baselines import design_guideline_layout
    from app.optimizer.encoding import Budget, grid_from_geometry
    from app.optimizer.ga import GAParams, run_ga

    osm_name, street_id = task
    base = {"osm_name": osm_name, "window_street_id": street_id}
    window, run, classes_1m, transform, residual_c = _window_context(street_id)
    try:
        grid = grid_from_geometry(window, run.model, classes_1m, transform, residual_c, street_name=osm_name)
    except (ValueError, IndexError) as error:
        return {**base, "skip": f"The design grid could not be built: {error}"}
    capacity = grid.tree_capacity()
    if capacity == 0:
        return {**base, "skip": "The cross-section has no plantable tree pits."}

    budget = grid.matched(Budget(trees=RANKING_REQUEST.trees_max, reflective_cells=0))
    params = GAParams(population=RANKING_REQUEST.population, generations=RANKING_REQUEST.generations, seed=RANKING_REQUEST.seed)
    ga = run_ga(grid, budget, params)
    searched = ga.objectives
    if searched.temp_delta_c_high >= 0:
        return {**base, "skip": "The searched layout gives no modelled cooling."}
    cooling_low, cooling_high = cooling_per_lakh_inr(searched.temp_delta_c_high, searched.cost_inr_low, searched.cost_inr_high)

    gradient = cooling_gradient(*crown_class_counts(grid, ga.genome), grid.n_cells)
    k = np.array([run.model.k_canopy_c_per_fraction, run.model.k_built_c_per_fraction, run.model.k_bare_c_per_fraction])
    if not math.isclose(float(gradient @ k), searched.temp_delta_c_high, abs_tol=1e-9):
        raise RuntimeError(f"{osm_name}: gradient reproduces {float(gradient @ k)} C, the layout gives {searched.temp_delta_c_high} C")
    k_covariance = run.covariance[1:, 1:]

    (start_e, start_n), (end_e, end_n) = grid.segment["start_utm"], grid.segment["end_utm"]
    lons, lats = warp_transform(window.bbox.crs, "EPSG:4326", [start_e, end_e], [start_n, end_n])
    return {
        **base,
        "segment_wgs84": ((round(lons[0], 6), round(lats[0], 6)), (round(lons[1], 6), round(lats[1], 6))),
        "highway": segment_highway(window, osm_name),
        "cross_section_source": grid.cross_section.source,
        "tree_capacity": capacity,
        "trees": searched.trees,
        "temp_delta_c": searched.temp_delta_c_high,
        "temp_delta_se_c": math.sqrt(max(float(gradient @ k_covariance @ gradient), 0.0)),
        "cooling_gradient": gradient.tolist(),
        "random_temp_delta_c": pipeline.random_arm(grid, budget).temp_delta_c_high,
        "design_guideline_temp_delta_c": grid.evaluate(design_guideline_layout(grid, budget)).temp_delta_c_high,
        "cost_inr_low": searched.cost_inr_low,
        "cost_inr_high": searched.cost_inr_high,
        "cooling_c_per_lakh_inr_low": cooling_low,
        "cooling_c_per_lakh_inr_high": cooling_high,
    }


def segment_highway(window, osm_name: str) -> str:
    from app.optimizer.encoding import segment_frame

    return segment_frame(window, osm_name)["way"]["tags"]["highway"]


def ranked(rows: list[dict], covariances: dict, z: float) -> list[RankedStreet]:
    """Sorted by cooling per lakh (high end), then by name, with ranks 1..n and the range each could hold.

    Every tree is priced at the same per-tree range, so cooling per lakh orders streets exactly as cooling per tree does,
    and ties are tested on cooling per tree, whose error comes only from the calibration coefficients.
    """
    rows = sorted(rows, key=lambda r: (-r["cooling_c_per_lakh_inr_high"], r["osm_name"]))
    per_tree_c = [-r["temp_delta_c"] / r["trees"] for r in rows]
    gradients = [-np.asarray(r["cooling_gradient"]) / r["trees"] for r in rows]
    intervals = rank_intervals(per_tree_c, gradients, [r["window_street_id"] for r in rows], covariances, z)
    streets = []
    for i, (row, (best, worst)) in enumerate(zip(rows, intervals), start=1):
        fields = {key: value for key, value in row.items() if key != "cooling_gradient"}
        streets.append(RankedStreet(rank=i, rank_best=min(best, i), rank_worst=max(worst, i), **fields))
    return streets


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    config.USE_LIVE_DATA = False

    from app.data.fixtures import load_window, street_manifest
    from app.pipeline import street_ids
    from app.snapshot import _git_commit

    fixture_ids = street_ids()
    windows = {s: load_window(s) for s in fixture_ids}
    tasks, skipped, too_short = candidates(windows)
    fixture_names = {(street_manifest(s)["osm_name"], s): s for s in fixture_ids}
    print(f"{len(tasks)} streets to rank, {len(skipped)} outside their window, {too_short} too short for a "
          f"{config.DESIGN_SEGMENT_LENGTH_M:.0f} m segment; {args.workers} workers", flush=True)

    rows, started = [], time.monotonic()
    with Pool(args.workers) as pool:
        for i, row in enumerate(pool.imap_unordered(_rank_one, tasks), start=1):
            if "skip" in row:
                skipped.append(SkippedStreet(osm_name=row["osm_name"], window_street_id=row["window_street_id"], reason=row["skip"]))
            else:
                rows.append({**row, "fixture_street_id": fixture_names.get((row["osm_name"], row["window_street_id"]))})
            print(f"  {i}/{len(tasks)} {row['osm_name']} ({row['window_street_id']}): "
                  f"{row.get('skip') or format(row['temp_delta_c'], '+.3f') + ' C'}  [{time.monotonic() - started:.0f} s]", flush=True)

    ranking_windows, covariances = [], {}
    for street_id, window in windows.items():
        run = _window_context(street_id)[1]
        covariances[street_id] = run.covariance[1:, 1:]
        calibration = run.result
        ranking_windows.append(RankingWindow(
            street_id=street_id, name=street_manifest(street_id)["name"], bbox_window=window.manifest["bbox_window"],
            rmse_holdout_c=calibration.rmse_holdout_c, rmse_mean_baseline_c=calibration.rmse_mean_baseline_c,
            provenance=calibration.provenance))

    ranking = StreetRanking(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        git_commit=_git_commit(),
        request=RANKING_REQUEST,
        windows=ranking_windows,
        streets=ranked(rows, covariances, config.RANKING_TIE_Z),
        skipped=sorted(skipped, key=lambda s: (s.window_street_id, s.osm_name)),
        resolution=Resolution(measurement_resolution_m=config.LANDSAT_CELL_SIZE_M,
                              calibration_resolution_m=config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M,
                              design_resolution_m=config.DESIGN_CELL_SIZE_M,
                              output_kind="model_output_at_design_resolution"),
    )
    config.RANKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RANKING_PATH.write_text(ranking.model_dump_json(), encoding="utf-8")
    print(f"wrote {config.RANKING_PATH}: {len(ranking.streets)} ranked, {len(ranking.skipped)} skipped", flush=True)


if __name__ == "__main__":
    main()
