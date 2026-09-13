"""Intervention delta: how each intervention changes modelled surface temperature, on top of the baseline.

  tree        the crown turns the cells beneath it into canopy; uses the fitted coefficients
  permeable   a paved footway becomes pervious ground, modelled as bare; uses the fitted k_bare
  reflective  surface albedo rises; uses the published albedo coefficient range, never a fitted one

Reflective effects therefore carry a low/high band; fitted effects are points. Every value is
the change in modelled land surface temperature, in °C, of the one design cell that changes.
"""

from dataclasses import dataclass

import numpy as np

from app import config
from app.data.landcover import BARE, BUILT, CANOPY, CARRIAGEWAY, FOOTWAY
from app.model.heat import HeatModel

# Existing surface assumed for each paved class when it is coated (docs/methodology.md).
EXISTING_MATERIAL = {CARRIAGEWAY: "asphalt_aged", FOOTWAY: "concrete_aged"}


@dataclass
class CellEffects:
    canopy_delta_c: np.ndarray
    reflective_delta_c_low: np.ndarray
    reflective_delta_c_high: np.ndarray
    permeable_delta_c: np.ndarray


def cell_effects(model: HeatModel, classes: np.ndarray) -> CellEffects:
    """Per-cell effect of each intervention. NaN where that intervention does not apply."""
    canopy_delta_c = np.zeros(classes.shape)
    canopy_delta_c[np.isin(classes, (CARRIAGEWAY, FOOTWAY))] = -model.k_canopy_c_per_fraction
    canopy_delta_c[classes == BARE] = -model.k_canopy_c_per_fraction - model.k_bare_c_per_fraction
    canopy_delta_c[classes == BUILT] = -model.k_canopy_c_per_fraction - model.k_built_c_per_fraction

    coating_low, coating_high = config.ALBEDO_BY_MATERIAL["high_albedo_coating"]
    reflective_delta_c_low = np.full(classes.shape, np.nan)
    reflective_delta_c_high = np.full(classes.shape, np.nan)
    for surface, material in EXISTING_MATERIAL.items():
        existing_low, existing_high = config.ALBEDO_BY_MATERIAL[material]
        cells = classes == surface
        # Most cooling: largest albedo gain with the high coefficient. Least: smallest gain with the low one.
        reflective_delta_c_low[cells] = -config.K_ALBEDO_HIGH_C_PER_UNIT_ALBEDO * (coating_high - existing_low)
        reflective_delta_c_high[cells] = -config.K_ALBEDO_LOW_C_PER_UNIT_ALBEDO * (coating_low - existing_high)

    permeable_delta_c = np.full(classes.shape, np.nan)
    permeable_delta_c[classes == FOOTWAY] = model.k_bare_c_per_fraction
    return CellEffects(canopy_delta_c, reflective_delta_c_low, reflective_delta_c_high, permeable_delta_c)


def before_lst_c(model: HeatModel, classes: np.ndarray, block_residual_c: np.ndarray) -> np.ndarray:
    """Modelled surface temperature of each design cell as it is today.

    The baseline model for the cell's surface class, plus the measured-minus-modelled residual of
    the 90 m calibration cell it sits in, so local heat the model does not explain is kept.
    """
    lst_c = np.full(classes.shape, model.t_base_c)
    lst_c[classes == CANOPY] -= model.k_canopy_c_per_fraction
    lst_c[classes == BUILT] += model.k_built_c_per_fraction
    lst_c[classes == BARE] += model.k_bare_c_per_fraction
    return lst_c + block_residual_c
