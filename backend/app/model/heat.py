"""Land surface temperature regression, calibrated on the 2 km neighbourhood window (SPEC.md §5).

    lst_pred_c = t_base_c
                 - k_canopy_c_per_fraction     * canopy_fraction
                 - k_albedo_c_per_unit_albedo  * delta_albedo
                 + k_impervious_c_per_fraction * impervious_fraction

delta_albedo is measured broadband albedo minus `albedo_reference` (the mean albedo of
the fitting pixels). So t_base_c is the modelled surface temperature of a cell with no
canopy, no impervious surface and reference albedo. With the signs written out above,
physically plausible fits have all three k values positive.

Fit on the neighbourhood window, never on one street's pixels (CLAUDE.md rule 8).
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HeatModel:
    t_base_c: float
    k_canopy_c_per_fraction: float
    k_albedo_c_per_unit_albedo: float
    k_impervious_c_per_fraction: float
    albedo_reference: float

    def predict_c(self, canopy_fraction, albedo, impervious_fraction) -> np.ndarray:
        return (self.t_base_c
                - self.k_canopy_c_per_fraction * np.asarray(canopy_fraction)
                - self.k_albedo_c_per_unit_albedo * (np.asarray(albedo) - self.albedo_reference)
                + self.k_impervious_c_per_fraction * np.asarray(impervious_fraction))


def design_matrix(canopy_fraction, albedo, impervious_fraction, albedo_reference: float) -> np.ndarray:
    """Columns match the model's signs, so least-squares coefficients are the k values directly."""
    canopy_fraction, albedo, impervious_fraction = (np.asarray(v, dtype=np.float64).ravel()
                                                    for v in (canopy_fraction, albedo, impervious_fraction))
    return np.column_stack([
        np.ones_like(canopy_fraction), -canopy_fraction, -(albedo - albedo_reference), impervious_fraction,
    ])


def fit(lst_c, canopy_fraction, albedo, impervious_fraction) -> tuple[HeatModel, np.ndarray]:
    """Ordinary least squares. Returns the model and the coefficient standard errors
    [t_base_c, k_canopy, k_albedo, k_impervious].

    The standard errors assume independent residuals. Landsat's thermal band is 100 m
    native, delivered at 30 m, so neighbouring pixels are not independent and these errors
    are optimistic; they are a diagnostic, not a confidence interval.
    """
    lst_c = np.asarray(lst_c, dtype=np.float64).ravel()
    albedo_reference = float(np.mean(albedo))
    x = design_matrix(canopy_fraction, albedo, impervious_fraction, albedo_reference)
    coefficients, _, rank, _ = np.linalg.lstsq(x, lst_c, rcond=None)
    if rank < x.shape[1]:
        raise ValueError(f"design matrix is rank {rank} of {x.shape[1]}; coefficients are not identifiable")
    residuals = lst_c - x @ coefficients
    dof = len(lst_c) - x.shape[1]
    covariance = (residuals @ residuals / dof) * np.linalg.inv(x.T @ x)
    model = HeatModel(
        t_base_c=float(coefficients[0]),
        k_canopy_c_per_fraction=float(coefficients[1]),
        k_albedo_c_per_unit_albedo=float(coefficients[2]),
        k_impervious_c_per_fraction=float(coefficients[3]),
        albedo_reference=albedo_reference,
    )
    return model, np.sqrt(np.diag(covariance))
