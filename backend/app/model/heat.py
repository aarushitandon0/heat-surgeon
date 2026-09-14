"""Baseline surface temperature model, calibrated on 90 m blocks of the neighbourhood window (SPEC.md §5).

    lst_pred_c = t_base_c
                 - k_canopy_c_per_fraction * canopy_fraction
                 + k_built_c_per_fraction  * built_fraction
                 + k_bare_c_per_fraction   * bare_fraction

Canopy, built, paved, bare and water fractions sum to one, so one class must be the reference: its
share is left out and every k is a difference from it. The model is written with paved as the reference
(t_base_c is a fully paved cell). Choosing another reference is a reparameterisation: predictions, error
and every pairwise difference between classes are unchanged; only which differences are reported as
"the coefficients", and their individual standard errors, change. reference_view() re-expresses the fit
against any class and contrasts() reports all pairs with standard errors.

There is no albedo term. Albedo could not be fitted from observation (docs/methodology.md), so
the effect of changing a surface's albedo is applied separately, with a published coefficient,
in app/model/delta.py.

Fit on the neighbourhood window, never on one street's pixels (CLAUDE.md rule 8).
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np

SURFACE_CLASSES = ("canopy", "built", "paved", "bare")

# Rows map the paved-reference coefficients [t_base, k_canopy, k_built, k_bare] to each class's modelled
# difference from a fully paved cell, in SURFACE_CLASSES order.
_EFFECT_FROM_COEFFICIENTS = np.array([
    [0.0, -1.0, 0.0, 0.0],   # canopy
    [0.0, 0.0, 1.0, 0.0],    # built
    [0.0, 0.0, 0.0, 0.0],    # paved
    [0.0, 0.0, 0.0, 1.0],    # bare
])


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

    @property
    def coefficients(self) -> np.ndarray:
        return np.array([self.t_base_c, self.k_canopy_c_per_fraction, self.k_built_c_per_fraction,
                         self.k_bare_c_per_fraction])


def design_matrix(canopy_fraction, built_fraction, bare_fraction) -> np.ndarray:
    """Columns match the model's signs, so least-squares coefficients are the k values directly."""
    canopy, built, bare = (np.asarray(v, dtype=np.float64).ravel() for v in (canopy_fraction, built_fraction, bare_fraction))
    return np.column_stack([np.ones_like(canopy), -canopy, built, bare])


def fit(lst_c, canopy_fraction, built_fraction, bare_fraction) -> tuple[HeatModel, np.ndarray, np.ndarray]:
    """Ordinary least squares. Returns the model, coefficient standard errors [t_base_c, k_canopy, k_built,
    k_bare], and their covariance matrix.

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
    return model, np.sqrt(np.diag(covariance)), covariance


def contrasts(model: HeatModel, covariance: np.ndarray) -> list[tuple[str, str, float, float]]:
    """(class_a, class_b, a minus b in °C for a full cell, standard error) for every pair of classes."""
    effects = _EFFECT_FROM_COEFFICIENTS @ model.coefficients
    effect_covariance = _EFFECT_FROM_COEFFICIENTS @ covariance @ _EFFECT_FROM_COEFFICIENTS.T
    out = []
    for i, j in combinations(range(len(SURFACE_CLASSES)), 2):
        variance = effect_covariance[i, i] + effect_covariance[j, j] - 2 * effect_covariance[i, j]
        out.append((SURFACE_CLASSES[i], SURFACE_CLASSES[j], float(effects[i] - effects[j]),
                    float(np.sqrt(max(variance, 0.0)))))
    return out


def reference_view(model: HeatModel, covariance: np.ndarray, reference: str) -> dict:
    """The same fit expressed with `reference` as the left-out class.

    {"t_reference_c": (value, se), "<class>": (value, se) for each other class}, where each value is that
    class minus the reference for a full cell.
    """
    r = SURFACE_CLASSES.index(reference)
    # Parameters: t_reference = t_base + effect_ref; each class minus reference = effect_c - effect_ref.
    rows = {"t_reference_c": np.array([1.0, 0, 0, 0]) + _EFFECT_FROM_COEFFICIENTS[r]}
    for c, name in enumerate(SURFACE_CLASSES):
        if c != r:
            rows[name] = _EFFECT_FROM_COEFFICIENTS[c] - _EFFECT_FROM_COEFFICIENTS[r]
    return {name: (float(row @ model.coefficients), float(np.sqrt(max(row @ covariance @ row, 0.0))))
            for name, row in rows.items()}
