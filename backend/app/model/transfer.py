"""Do calibrated coefficients transfer between neighbourhoods? (docs/methodology.md, "Transfer test")

    python -m app.model.transfer

For every target window, scored on that window's own held-out 90 m cells (the same seeded split its calibration
reports), compare:

- own: the target's own fit, the number the product reports as rmse_holdout_c
- mean: the target's mean-prediction baseline
- <source> raw: another window's fitted model applied unchanged
- <source> offset: that model with only t_base_c refitted on the target's fitting cells
- pooled raw / offset: one model fitted on the other three windows together (leave one window out)

Source cells whose centre lies inside the target window are dropped before fitting, so overlapping windows cannot
leak the target's own pixels into a "transferred" model. Runs offline from fixtures.
"""

import argparse
from dataclasses import dataclass, replace

import numpy as np

from app import config
from app.contracts import CalibrationRequest
from app.data.fixtures import load_window
from app.model.heat import HeatModel, fit
from app.model.validate import UsableCells, holdout_split, rmse_c, usable_cells
from app.pipeline import street_ids

BLOCK_M = config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M


def block_centres_m(block_index: np.ndarray, block_shape: tuple[int, int], bounds_m: tuple[float, float, float, float],
                    block_m: float) -> tuple[np.ndarray, np.ndarray]:
    """(easting, northing) of each block's centre. Blocks run row-major from the window's north-west corner."""
    min_e_m, min_n_m, max_e_m, max_n_m = bounds_m
    if not (min_e_m < max_e_m and min_n_m < max_n_m):
        raise ValueError(f"bounds_m must be [min_e, min_n, max_e, max_n], got {bounds_m}")
    rows, cols = np.divmod(np.asarray(block_index), block_shape[1])
    return min_e_m + (cols + 0.5) * block_m, max_n_m - (rows + 0.5) * block_m


def inside_bounds(e_m: np.ndarray, n_m: np.ndarray, bounds_m: tuple[float, float, float, float]) -> np.ndarray:
    min_e_m, min_n_m, max_e_m, max_n_m = bounds_m
    return (e_m >= min_e_m) & (e_m <= max_e_m) & (n_m >= min_n_m) & (n_m <= max_n_m)


def offset_adjusted(model: HeatModel, observed_c: np.ndarray, canopy_fraction, built_fraction, bare_fraction) -> HeatModel:
    """The same k coefficients with t_base_c shifted so the mean residual on these cells is zero."""
    shift_c = float(np.mean(np.asarray(observed_c) - model.predict_c(canopy_fraction, built_fraction, bare_fraction)))
    return replace(model, t_base_c=model.t_base_c + shift_c)


@dataclass
class Window:
    street_id: str
    bounds_m: tuple[float, float, float, float]
    usable: UsableCells
    fit_i: np.ndarray
    holdout_i: np.ndarray
    e_m: np.ndarray
    n_m: np.ndarray

    def covers(self, i: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        c = self.usable.cells
        return c["canopy_fraction"][i], c["built_fraction"][i], c["bare_fraction"][i]

    def lst_c(self, i: np.ndarray) -> np.ndarray:
        return self.usable.cells["lst_c"][i]


def load(street_id: str, request: CalibrationRequest) -> Window:
    window = load_window(street_id)
    usable = usable_cells(window)
    bounds_m = tuple(float(v) for v in window.manifest["window"]["bounds_m"])
    fit_i, holdout_i = holdout_split(len(usable.block_index), request.holdout_fraction, request.seed)
    e_m, n_m = block_centres_m(usable.block_index, usable.block_shape, bounds_m, BLOCK_M)
    return Window(street_id, bounds_m, usable, fit_i, holdout_i, e_m, n_m)


def source_fit_cells(source: Window, target: Window) -> np.ndarray:
    """The source's fitting cells whose centre lies outside the target window."""
    outside = ~inside_bounds(source.e_m[source.fit_i], source.n_m[source.fit_i], target.bounds_m)
    return source.fit_i[outside]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    request = CalibrationRequest()
    windows = {s: load(s, request) for s in street_ids()}

    print("| Target | Own | Mean | Source | Source cells used | Raw | Offset |")
    print("|---|---|---|---|---|---|---|")
    pooled_rows = []
    for target in windows.values():
        t_obs_c = target.lst_c(target.holdout_i)
        own, _, _ = fit(target.lst_c(target.fit_i), *target.covers(target.fit_i))
        own_c = rmse_c(t_obs_c, own.predict_c(*target.covers(target.holdout_i)))
        mean_c = rmse_c(t_obs_c, np.full(len(t_obs_c), target.lst_c(target.fit_i).mean()))

        pooled_obs, pooled_cover = [], [[], [], []]
        for source in windows.values():
            if source is target:
                continue
            used = source_fit_cells(source, target)
            pooled_obs.append(source.lst_c(used))
            for k, v in enumerate(source.covers(used)):
                pooled_cover[k].append(v)
            model, _, _ = fit(source.lst_c(used), *source.covers(used))
            raw_c = rmse_c(t_obs_c, model.predict_c(*target.covers(target.holdout_i)))
            shifted = offset_adjusted(model, target.lst_c(target.fit_i), *target.covers(target.fit_i))
            offset_c = rmse_c(t_obs_c, shifted.predict_c(*target.covers(target.holdout_i)))
            print(f"| {target.street_id} | {own_c:.2f} | {mean_c:.2f} | {source.street_id} | {len(used)} of {len(source.fit_i)} "
                  f"| {raw_c:.2f} | {offset_c:.2f} |")

        pooled, _, _ = fit(np.concatenate(pooled_obs), *(np.concatenate(v) for v in pooled_cover))
        pooled_raw_c = rmse_c(t_obs_c, pooled.predict_c(*target.covers(target.holdout_i)))
        pooled_shifted = offset_adjusted(pooled, target.lst_c(target.fit_i), *target.covers(target.fit_i))
        pooled_offset_c = rmse_c(t_obs_c, pooled_shifted.predict_c(*target.covers(target.holdout_i)))
        pooled_rows.append((target.street_id, own_c, mean_c, pooled_raw_c, pooled_offset_c, own, pooled))

    print("\n| Target | Own | Mean | Pooled other three, raw | Pooled, offset |")
    print("|---|---|---|---|---|")
    for street_id, own_c, mean_c, raw_c, offset_c, _, _ in pooled_rows:
        print(f"| {street_id} | {own_c:.2f} | {mean_c:.2f} | {raw_c:.2f} | {offset_c:.2f} |")

    print("\n| Window | t_base_c | k_canopy | k_built | k_bare | Cells fit |")
    print("|---|---|---|---|---|---|")
    for (street_id, *_, own, _), window in zip(pooled_rows, windows.values()):
        print(f"| {street_id} | {own.t_base_c:.2f} | {own.k_canopy_c_per_fraction:.2f} | {own.k_built_c_per_fraction:.2f} "
              f"| {own.k_bare_c_per_fraction:.2f} | {len(window.fit_i)} |")


if __name__ == "__main__":
    main()
