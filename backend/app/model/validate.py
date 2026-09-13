"""Hold-out error reporting (SPEC.md §5.4) and the calibration CLI.

    python -m app.model.validate --street pune-fc-road

Fits the heat model on a random (1 - holdout_fraction) share of the neighbourhood
window's usable pixels, predicts the rest, and reports rmse_holdout_c,
rmse_mean_baseline_c and r2_holdout. The mean baseline predicts every held-out pixel as
the mean of the fitting pixels, so neither error sees held-out data during fitting.
Runs offline from fixtures.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config
from app.contracts import CalibrationRequest, CalibrationResult
from app.data.fixtures import load_window
from app.data.landcover import land_cover_fractions
from app.model.heat import HeatModel, fit

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
        raise ValueError(f"holdout of {n_holdout} from {n} pixels leaves nothing to fit or to test")
    order = np.random.default_rng(seed).permutation(n)
    return np.sort(order[n_holdout:]), np.sort(order[:n_holdout])


@dataclass
class CalibrationRun:
    result: CalibrationResult
    model: HeatModel
    standard_errors: np.ndarray
    rmse_fit_c: float
    observed_fit_c: np.ndarray
    predicted_fit_c: np.ndarray
    observed_holdout_c: np.ndarray
    predicted_holdout_c: np.ndarray
    excluded: dict[str, int]
    regressors: dict[str, np.ndarray]


def calibrate(street_id: str, request: CalibrationRequest | None = None) -> CalibrationRun:
    request = request or CalibrationRequest()
    window = load_window(street_id)
    landsat, s2 = window.landsat, window.sentinel2
    lst_c = landsat.arrays["lst_c"].astype(np.float64)
    albedo = landsat.arrays["albedo"].astype(np.float64)
    cover = land_cover_fractions(
        s2.arrays["red"], s2.arrays["nir"], tuple(s2.metadata["transform"]), s2.metadata["boa_add_offset_applied"],
        tuple(landsat.metadata["transform"]), lst_c.shape,
    )

    measured = np.isfinite(lst_c) & np.isfinite(albedo)
    covered = cover.valid_fraction == 1.0  # every part of the 30 m cell observed by Sentinel-2
    dry = cover.water_fraction <= config.WATER_FRACTION_MAX_FOR_FIT
    usable = measured & covered & dry
    excluded = {
        "no Landsat value": int((~measured).sum()),
        "incomplete Sentinel-2 cover": int((measured & ~covered).sum()),
        "water": int((measured & covered & ~dry).sum()),
    }

    index = np.flatnonzero(usable)
    observed = lst_c.ravel()[index]
    regressors = {
        "canopy_fraction": cover.canopy_fraction.ravel()[index],
        "albedo": albedo.ravel()[index],
        "impervious_fraction": cover.impervious_fraction.ravel()[index],
    }
    fit_i, holdout_i = holdout_split(len(index), request.holdout_fraction, request.seed)

    def subset(i):
        return regressors["canopy_fraction"][i], regressors["albedo"][i], regressors["impervious_fraction"][i]

    model, standard_errors = fit(observed[fit_i], *subset(fit_i))
    predicted_fit, predicted_holdout = model.predict_c(*subset(fit_i)), model.predict_c(*subset(holdout_i))
    baseline = np.full(len(holdout_i), observed[fit_i].mean())

    result = CalibrationResult(
        street_id=street_id,
        bbox_window=window.manifest["bbox_window"],
        k_canopy_c_per_fraction=model.k_canopy_c_per_fraction,
        k_albedo_c_per_unit_albedo=model.k_albedo_c_per_unit_albedo,
        k_impervious_c_per_fraction=model.k_impervious_c_per_fraction,
        t_base_c=model.t_base_c,
        rmse_holdout_c=rmse_c(observed[holdout_i], predicted_holdout),
        rmse_mean_baseline_c=rmse_c(observed[holdout_i], baseline),
        r2_holdout=r2_score(observed[holdout_i], predicted_holdout),
        n_pixels_fit=len(fit_i),
        n_pixels_holdout=len(holdout_i),
        provenance=[window.landsat_provenance, window.sentinel2_provenance],
    )
    return CalibrationRun(
        result=result, model=model, standard_errors=standard_errors,
        rmse_fit_c=rmse_c(observed[fit_i], predicted_fit),
        observed_fit_c=observed[fit_i], predicted_fit_c=predicted_fit,
        observed_holdout_c=observed[holdout_i], predicted_holdout_c=predicted_holdout,
        excluded=excluded, regressors={**regressors, "lst_c": observed},
    )


def save_scatter(run: CalibrationRun, street_name: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    r = run.result
    fig, ax = plt.subplots(figsize=(6.5, 6.8), dpi=150)
    ax.scatter(run.observed_fit_c, run.predicted_fit_c, s=5, color="#BBBBBB", linewidths=0,
               label=f"Fitting pixels (n = {r.n_pixels_fit})")
    ax.scatter(run.observed_holdout_c, run.predicted_holdout_c, s=7, color="#1B4B57", linewidths=0,
               label=f"Held-out pixels (n = {r.n_pixels_holdout})")
    values = np.concatenate([run.observed_fit_c, run.predicted_fit_c, run.observed_holdout_c, run.predicted_holdout_c])
    low, high = np.floor(values.min()), np.ceil(values.max())
    ax.plot([low, high], [low, high], color="#444444", linewidth=1, label="Modelled equals observed")
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_aspect("equal")
    ax.set_xlabel("Observed land surface temperature (°C)\nLandsat per-pixel median, March to May 2024 to 2026, 30 m")
    ax.set_ylabel("Modelled land surface temperature (°C)")
    ax.set_title(f"{street_name}: 2 km neighbourhood window, modelled against observed", loc="left", fontsize=10)
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
    parser = argparse.ArgumentParser(description="Calibrate the heat model on a street's cached neighbourhood window.")
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

    total = sum(run.excluded.values()) + r.n_pixels_fit + r.n_pixels_holdout
    print(f"Calibration  {args.street} ({name}), 2 km neighbourhood window, surface temperature")
    print(f"Pixels       {r.n_pixels_fit + r.n_pixels_holdout} usable of {total}; excluded "
          + ", ".join(f"{k} {v}" for k, v in run.excluded.items()))
    print(f"             fit {r.n_pixels_fit}, held out {r.n_pixels_holdout} "
          f"(holdout_fraction {args.holdout_fraction}, seed {args.seed})")
    print()
    print("Model        lst_pred_c = t_base_c - k_canopy * canopy - k_albedo * (albedo - reference) + k_impervious * impervious")
    print(f"  t_base_c                     {m.t_base_c:8.3f} °C                       (se {se[0]:.3f})")
    print(f"  k_canopy_c_per_fraction      {m.k_canopy_c_per_fraction:8.3f} °C per unit canopy fraction  (se {se[1]:.3f})")
    print(f"  k_albedo_c_per_unit_albedo   {m.k_albedo_c_per_unit_albedo:8.3f} °C per unit albedo          (se {se[2]:.3f})")
    print(f"  k_impervious_c_per_fraction  {m.k_impervious_c_per_fraction:8.3f} °C per unit impervious fraction (se {se[3]:.3f})")
    print(f"  albedo reference             {m.albedo_reference:8.4f} (mean albedo of fitting pixels)")
    print()
    print("Error, held-out pixels")
    print(f"  rmse_holdout_c               {r.rmse_holdout_c:8.3f} °C")
    print(f"  rmse_mean_baseline_c         {r.rmse_mean_baseline_c:8.3f} °C")
    print(f"  r2_holdout                   {r.r2_holdout:8.3f}")
    print(f"  rmse on fitting pixels       {run.rmse_fit_c:8.3f} °C")
    print()
    names = ["canopy_fraction", "albedo", "impervious_fraction", "lst_c"]
    stack = np.vstack([run.regressors[n] for n in names])
    print("Regressors over usable pixels (mean, standard deviation)")
    for n, row in zip(names, stack):
        print(f"  {n:20s} {row.mean():8.4f} {row.std():8.4f}")
    print("Correlation   " + "  ".join(f"{n[:10]:>10s}" for n in names))
    for n, row in zip(names, np.corrcoef(stack)):
        print(f"  {n[:10]:10s}  " + "  ".join(f"{v:10.3f}" for v in row))
    print()
    print(f"Scatter      {figure.relative_to(REPO_DIR).as_posix()}")
    print("Note         Standard errors assume independent residuals. Neighbouring 30 m pixels share a 100 m "
          "thermal footprint, so they are optimistic.")


if __name__ == "__main__":
    main()
