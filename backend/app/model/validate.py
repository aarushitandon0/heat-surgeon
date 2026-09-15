"""Hold-out error reporting (SPEC.md §5.4) and the calibration CLI.

    python -m app.model.validate --street pune-fc-road

Calibration cells are 90 m blocks (3 x 3 Landsat cells), close to the thermal band's 100 m
native resolution. Surface temperature is the mean of the block's measured cells; surface
cover fractions are exact area shares. The baseline model is fitted on a random
(1 - holdout_fraction) share of usable blocks and scored on the rest. The mean baseline
predicts every held-out block as the mean of the fitting blocks. Runs offline from fixtures.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config
from app.contracts import CalibrationRequest, CalibrationResult, SurfaceContrast
from app.data.fixtures import CachedWindow, load_window
from app.data.landcover import SurfaceCover, block_fractions, block_mean, classify_surfaces
from app.model.heat import SURFACE_CLASSES, HeatModel, contrasts, fit, reference_view

REPO_DIR = config.BACKEND_DIR.parent


def rmse_c(observed_c: np.ndarray, predicted_c: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(observed_c) - np.asarray(predicted_c)) ** 2)))


def r2_score(observed: np.ndarray, predicted: np.ndarray) -> float:
    observed, predicted = np.asarray(observed), np.asarray(predicted)
    residual = np.sum((observed - predicted) ** 2)
    total = np.sum((observed - observed.mean()) ** 2)
    return float(1 - residual / total)


def holdout_split(n: int, holdout_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic random split of range(n) into (fit, holdout) index arrays."""
    n_holdout = int(round(n * holdout_fraction))
    if not 0 < n_holdout < n:
        raise ValueError(f"holdout of {n_holdout} from {n} cells leaves nothing to fit or to test")
    order = np.random.default_rng(seed).permutation(n)
    return np.sort(order[n_holdout:]), np.sort(order[:n_holdout])


def window_surfaces(window: CachedWindow) -> tuple[np.ndarray, object]:
    """Surface class codes on the 1 m sub-grid of the whole window."""
    s2 = window.sentinel2
    return classify_surfaces(s2.arrays["red"], s2.arrays["nir"], tuple(s2.metadata["transform"]),
                             s2.metadata["boa_add_offset_applied"], window.surface_geometry, window.bbox.bounds)


def calibration_cells(window: CachedWindow, classes: np.ndarray | None = None) -> tuple[SurfaceCover, np.ndarray, np.ndarray]:
    """(surface cover fractions, mean surface temperature, mean albedo) per 90 m calibration cell."""
    if classes is None:
        classes, _ = window_surfaces(window)
    block_px = round(config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M / config.SURFACE_SUBGRID_M)
    cover = block_fractions(classes, block_px)
    lst_c = block_mean(window.landsat.arrays["lst_c"], config.CALIBRATION_BLOCK_CELLS)
    albedo = block_mean(window.landsat.arrays["albedo"], config.CALIBRATION_BLOCK_CELLS)
    if cover.canopy_fraction.shape != lst_c.shape:
        raise ValueError(f"surface cover blocks {cover.canopy_fraction.shape} do not match thermal blocks {lst_c.shape}")
    return cover, lst_c, albedo


@dataclass
class CalibrationRun:
    result: CalibrationResult
    model: HeatModel
    standard_errors: np.ndarray
    covariance: np.ndarray
    mean_share: dict[str, float]
    footprint_counts: dict
    rmse_fit_c: float
    observed_fit_c: np.ndarray
    predicted_fit_c: np.ndarray
    observed_holdout_c: np.ndarray
    predicted_holdout_c: np.ndarray
    excluded: dict[str, int]
    cells: dict[str, np.ndarray]
    albedo_correlation: dict[str, tuple[int, float]]


@dataclass
class UsableCells:
    """The 90 m calibration cells a fit may use, as flat arrays, and where each sits in the block grid."""
    cells: dict[str, np.ndarray]
    block_index: np.ndarray   # flat index into the block grid, row-major from the window's north-west corner
    block_shape: tuple[int, int]
    excluded: dict[str, int]


def usable_cells(window: CachedWindow) -> UsableCells:
    cover, lst_c, albedo = calibration_cells(window)
    measured = np.isfinite(lst_c) & np.isfinite(albedo)
    covered = cover.observed_fraction == 1.0
    dry = cover.water_fraction <= config.WATER_FRACTION_MAX_FOR_FIT
    usable = measured & covered & dry
    excluded = {
        "no Landsat value": int((~measured).sum()),
        "incomplete Sentinel-2 cover": int((measured & ~covered).sum()),
        "water": int((measured & covered & ~dry).sum()),
    }
    index = np.flatnonzero(usable)
    cells = {
        "canopy_fraction": cover.canopy_fraction.ravel()[index],
        "built_fraction": cover.built_fraction.ravel()[index],
        "paved_fraction": cover.paved_fraction.ravel()[index],
        "bare_fraction": cover.bare_fraction.ravel()[index],
        "albedo": albedo.ravel()[index],
        "lst_c": lst_c.ravel()[index],
    }
    return UsableCells(cells=cells, block_index=index, block_shape=lst_c.shape, excluded=excluded)


def calibrate(street_id: str, request: CalibrationRequest | None = None) -> CalibrationRun:
    request = request or CalibrationRequest()
    window = load_window(street_id)
    usable = usable_cells(window)
    cells, index, excluded = usable.cells, usable.block_index, usable.excluded
    observed = cells["lst_c"]
    fit_i, holdout_i = holdout_split(len(index), request.holdout_fraction, request.seed)

    def subset(i):
        return cells["canopy_fraction"][i], cells["built_fraction"][i], cells["bare_fraction"][i]

    model, standard_errors, covariance = fit(observed[fit_i], *subset(fit_i))
    predicted_fit, predicted_holdout = model.predict_c(*subset(fit_i)), model.predict_c(*subset(holdout_i))
    baseline = np.full(len(holdout_i), observed[fit_i].mean())
    # Report against the best-supported class: the one with the largest mean share of the fitting cells.
    mean_share = {name: float(cells[f"{name}_fraction"][fit_i].mean()) for name in SURFACE_CLASSES}
    reference = max(mean_share, key=mean_share.get)
    pairs = contrasts(model, covariance)

    albedo_correlation = {}
    for name in ("built_fraction", "paved_fraction", "bare_fraction", "canopy_fraction"):
        members = cells[name] >= config.BUILT_DOMINANT_FRACTION
        n = int(members.sum())
        corr = float(np.corrcoef(cells["albedo"][members], observed[members])[0, 1]) if n >= 3 else float("nan")
        albedo_correlation[name] = (n, corr)

    result = CalibrationResult(
        street_id=street_id,
        bbox_window=window.manifest["bbox_window"],
        calibration_resolution_m=config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M,
        t_base_c=model.t_base_c,
        k_canopy_c_per_fraction=model.k_canopy_c_per_fraction,
        k_built_c_per_fraction=model.k_built_c_per_fraction,
        k_bare_c_per_fraction=model.k_bare_c_per_fraction,
        k_albedo_low_c_per_unit_albedo=config.K_ALBEDO_LOW_C_PER_UNIT_ALBEDO,
        k_albedo_high_c_per_unit_albedo=config.K_ALBEDO_HIGH_C_PER_UNIT_ALBEDO,
        rmse_holdout_c=rmse_c(observed[holdout_i], predicted_holdout),
        rmse_mean_baseline_c=rmse_c(observed[holdout_i], baseline),
        r2_holdout=r2_score(observed[holdout_i], predicted_holdout),
        n_cells_fit=len(fit_i),
        n_cells_holdout=len(holdout_i),
        fit_reference_class=reference,
        contrasts=[SurfaceContrast(class_a=a, class_b=b, difference_c=d, standard_error_c=se) for a, b, d, se in pairs],
        building_footprint_sources=sorted({b["footprint_source"] for b in window.buildings}),
        provenance=[window.landsat_provenance, window.sentinel2_provenance],
    )
    return CalibrationRun(
        result=result, model=model, standard_errors=standard_errors, covariance=covariance,
        mean_share=mean_share, footprint_counts=window.footprint_counts,
        rmse_fit_c=rmse_c(observed[fit_i], predicted_fit),
        observed_fit_c=observed[fit_i], predicted_fit_c=predicted_fit,
        observed_holdout_c=observed[holdout_i], predicted_holdout_c=predicted_holdout,
        excluded=excluded, cells=cells, albedo_correlation=albedo_correlation,
    )


def save_scatter(run: CalibrationRun, street_name: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    r = run.result
    fig, ax = plt.subplots(figsize=(6.5, 6.8), dpi=150)
    ax.scatter(run.observed_fit_c, run.predicted_fit_c, s=12, color="#BBBBBB", linewidths=0,
               label=f"Fitting cells (n = {r.n_cells_fit})")
    ax.scatter(run.observed_holdout_c, run.predicted_holdout_c, s=16, color="#1B4B57", linewidths=0,
               label=f"Held-out cells (n = {r.n_cells_holdout})")
    values = np.concatenate([run.observed_fit_c, run.predicted_fit_c, run.observed_holdout_c, run.predicted_holdout_c])
    low, high = np.floor(values.min()), np.ceil(values.max())
    ax.plot([low, high], [low, high], color="#444444", linewidth=1, label="Modelled equals observed")
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_aspect("equal")
    ax.set_xlabel("Observed land surface temperature (°C)\nLandsat per-pixel median, March to May 2024 to 2026, "
                  "mean over 90 m cells")
    ax.set_ylabel("Modelled land surface temperature (°C)")
    ax.set_title(f"{street_name}: baseline model on 90 m cells, modelled against observed", loc="left", fontsize=10)
    ax.text(0.03, 0.97,
            f"Hold-out RMSE {r.rmse_holdout_c:.2f} °C\nMean-prediction baseline {r.rmse_mean_baseline_c:.2f} °C\n"
            f"Hold-out R² {r.r2_holdout:.2f}",
            transform=ax.transAxes, va="top", fontsize=9)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Calibrate the baseline heat model on a street's cached window.")
    parser.add_argument("--street", required=True)
    parser.add_argument("--holdout-fraction", type=float, default=CalibrationRequest().holdout_fraction)
    parser.add_argument("--seed", type=int, default=CalibrationRequest().seed)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    run = calibrate(args.street, CalibrationRequest(holdout_fraction=args.holdout_fraction, seed=args.seed))
    r, m, se = run.result, run.model, run.standard_errors
    name = load_window(args.street).manifest["name"]
    figure = REPO_DIR / "docs" / "figures" / f"{args.street}-calibration.png"
    save_scatter(run, name, figure)

    total = sum(run.excluded.values()) + r.n_cells_fit + r.n_cells_holdout
    print(f"Calibration  {args.street} ({name}), baseline surface temperature model, 90 m cells")
    print(f"Cells        {r.n_cells_fit + r.n_cells_holdout} usable of {total}; excluded "
          + ", ".join(f"{k} {v}" for k, v in run.excluded.items()))
    print(f"             fit {r.n_cells_fit}, held out {r.n_cells_holdout} "
          f"(holdout_fraction {args.holdout_fraction}, seed {args.seed})")
    print()
    fc = run.footprint_counts
    print("Footprints   " + ", ".join(f"{k} {v}" for k, v in fc.items()))
    print("Mean share   " + ", ".join(f"{k} {v:.3f}" for k, v in run.mean_share.items())
          + f"  -> reference class: {r.fit_reference_class}")
    print()
    view = reference_view(m, run.covariance, r.fit_reference_class)
    t_ref, t_ref_se = view.pop("t_reference_c")
    print(f"Model, {r.fit_reference_class} as reference (a reparameterisation; predictions identical)")
    print(f"  fully {r.fit_reference_class} cell          {t_ref:8.3f} °C   (se {t_ref_se:.3f})")
    for name, (value, value_se) in view.items():
        print(f"  {name:8s} minus {r.fit_reference_class:8s}     {value:+8.3f} °C   (se {value_se:.3f})")
    print()
    print("Contract fields (paved as reference)")
    print(f"  t_base_c                     {m.t_base_c:8.3f} °C (fully paved cell)   (se {se[0]:.3f})")
    print(f"  k_canopy_c_per_fraction      {m.k_canopy_c_per_fraction:8.3f}                           (se {se[1]:.3f})")
    print(f"  k_built_c_per_fraction       {m.k_built_c_per_fraction:8.3f}                           (se {se[2]:.3f})")
    print(f"  k_bare_c_per_fraction        {m.k_bare_c_per_fraction:8.3f}                           (se {se[3]:.3f})")
    print(f"  k_albedo (published, fixed)  {r.k_albedo_low_c_per_unit_albedo:.1f} to {r.k_albedo_high_c_per_unit_albedo:.1f} °C per unit albedo")
    print()
    print("All pairwise contrasts, full cell of a minus full cell of b")
    for c in r.contrasts:
        z = abs(c.difference_c) / c.standard_error_c if c.standard_error_c else float("inf")
        print(f"  {c.class_a:7s} - {c.class_b:7s} {c.difference_c:+8.3f} °C  (se {c.standard_error_c:.3f}, |z| {z:.1f})")
    print()
    print("Error, held-out cells")
    print(f"  rmse_holdout_c               {r.rmse_holdout_c:8.3f} °C")
    print(f"  rmse_mean_baseline_c         {r.rmse_mean_baseline_c:8.3f} °C")
    print(f"  r2_holdout                   {r.r2_holdout:8.3f}")
    print(f"  rmse on fitting cells        {run.rmse_fit_c:8.3f} °C")
    print()
    names = ["canopy_fraction", "built_fraction", "paved_fraction", "bare_fraction", "albedo", "lst_c"]
    print("Cells (mean, standard deviation)")
    for n in names:
        print(f"  {n:16s} {run.cells[n].mean():8.4f} {run.cells[n].std():8.4f}")
    print("Correlation      " + " ".join(f"{n[:9]:>9s}" for n in names))
    for n, row in zip(names, np.corrcoef(np.vstack([run.cells[n] for n in names]))):
        print(f"  {n[:14]:14s} " + " ".join(f"{v:9.3f}" for v in row))
    print()
    print(f"Albedo against surface temperature within cells at least {config.BUILT_DOMINANT_FRACTION:.0%} of one class")
    for n, (count, corr) in run.albedo_correlation.items():
        print(f"  {n:16s} n={count:4d}  r={corr:+.3f}")
    print("  (diagnostic only; the Sentinel-2 B11 escalation rule was retired for building footprints, Day 4)")
    print()
    print(f"Scatter      {figure.relative_to(REPO_DIR).as_posix()}")


if __name__ == "__main__":
    main()
