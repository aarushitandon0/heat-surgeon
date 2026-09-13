"""Baseline surface temperature model, calibrated on 90 m blocks of the neighbourhood window (SPEC.md §5).

    lst_pred_c = t_base_c
                 - k_canopy_c_per_fraction * canopy_fraction
                 + k_built_c_per_fraction  * built_fraction
                 + k_bare_c_per_fraction   * bare_fraction

Canopy, built, paved, bare and water fractions sum to one, so paved surface is the reference
class: t_base_c is the modelled surface temperature of a fully paved cell, and each k is the
difference from paved. With the signs written above, canopy cooler than paving gives a
positive k_canopy; built or bare surface hotter than paving gives a positive k_built or k_bare.

There is no albedo term. Albedo could not be fitted from observation (docs/methodology.md), so
the effect of changing a surface's albedo is applied separately, with a published coefficient,
in app/model/delta.py.

Fit on the neighbourhood window, never on one street's pixels (CLAUDE.md rule 8).
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HeatModel:
    t_base_c: float
    k_canopy_c_per_fraction: float
    k_built_c_per_fraction: float
    k_bare_c_per_fraction: float

    def predict_c(self, canopy_fraction, built_fraction, bare_fraction) -> np.ndarray:
        return (self.t_base_c
                - self.k_canopy_c_per_fraction * np.asarray(canopy_fraction)
                + self.k_built_c_per_fraction * np.asarray(built_fraction)
                + self.k_bare_c_per_fraction * np.asarray(bare_fraction))


def design_matrix(canopy_fraction, built_fraction, bare_fraction) -> np.ndarray:
    """Columns match the model's signs, so least-squares coefficients are the k values directly."""
    canopy, built, bare = (np.asarray(v, dtype=np.float64).ravel() for v in (canopy_fraction, built_fraction, bare_fraction))
    return np.column_stack([np.ones_like(canopy), -canopy, built, bare])


def fit(lst_c, canopy_fraction, built_fraction, bare_fraction) -> tuple[HeatModel, np.ndarray]:
    """Ordinary least squares. Returns the model and coefficient standard errors
    [t_base_c, k_canopy, k_built, k_bare].

    The standard errors assume independent residuals. Neighbouring 90 m blocks still share some
    thermal signal, so they are a diagnostic, not a confidence interval.
    """
    lst_c = np.asarray(lst_c, dtype=np.float64).ravel()
    x = design_matrix(canopy_fraction, built_fraction, bare_fraction)
    coefficients, _, rank, _ = np.linalg.lstsq(x, lst_c, rcond=None)
    if rank < x.shape[1]:
        raise ValueError(f"design matrix is rank {rank} of {x.shape[1]}; coefficients are not identifiable")
    residuals = lst_c - x @ coefficients
    dof = len(lst_c) - x.shape[1]
    covariance = (residuals @ residuals / dof) * np.linalg.inv(x.T @ x)
    model = HeatModel(
        t_base_c=float(coefficients[0]),
        k_canopy_c_per_fraction=float(coefficients[1]),
        k_built_c_per_fraction=float(coefficients[2]),
        k_bare_c_per_fraction=float(coefficients[3]),
    )
    return model, np.sqrt(np.diag(covariance))
