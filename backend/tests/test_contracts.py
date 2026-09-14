"""Contract shapes: invariants raise, unit suffixes are enforced, the TypeScript mirror stays in sync.

Values here are synthetic test fixtures, not data.
"""

import re
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from app import contracts
from app.contracts import (
    ComparisonArm,
    DesignGrid,
    OptimizationResult,
    OptimizeMessage,
    OptimizeProgress,
    Provenance,
    ThermalGrid,
)

TS_CONTRACTS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "contracts.ts"

UNIT_SUFFIX = re.compile(
    r"_(c|c_low|c_high|m|m2|deg|inr|inr_low|inr_high|inr_max|c_per_fraction|c_per_unit_albedo|c_per_inr)$"
)
DIMENSIONLESS = {
    "scene_count", "valid_pixels", "n_cells_fit", "n_cells_holdout", "generation", "generations",
    "generations_total", "population", "cells", "states_per_cell", "seed",
    "holdout_fraction", "r2_holdout", "best_fitness_score", "trees", "reflective_cells",
    "trees_max", "reflective_cells_max",
}


def provenance(**overrides):
    data = {
        "product": "surface_temperature",
        "date_range": ["2024-03-01", "2026-05-31"],
        "months": [3, 4, 5],
        "scene_count": 2,
        "capture_dates": ["2024-03-14", "2024-03-30"],
        "scene_ids": ["scene-a", "scene-b"],
        "collections": ["landsat-c2-l2"],
        "platforms": ["landsat-8", "landsat-9"],
        "compositing": "per-pixel median",
        "cloud_masking": "QA_PIXEL bitmask",
        "overpass_local_time": "10:30",
        "native_resolution_m": 100,
        "delivered_resolution_m": 30,
        "source_adapter": "planetary_computer",
    }
    return {**data, **overrides}


def thermal_grid(**overrides):
    data = {
        "street_id": "test-street",
        "scope": "window",
        "crs": "EPSG:32643",
        "transform": [30.0, 0.0, 373185.0, 0.0, -30.0, 2051925.0],
        "shape": [2, 3],
        "cell_size_m": 30.0,
        "bbox_wgs84": [73.83, 18.51, 73.85, 18.53],
        "lst_c": [[30.1, None, 31.0], [29.5, 30.0, None]],
        "stats": {"min_c": 29.5, "max_c": 31.0, "mean_c": 30.15, "valid_pixels": 4},
        "provenance": provenance(),
    }
    return {**data, **overrides}


def arm(delta_c, low, high):
    return {"temp_delta_c_low": delta_c, "temp_delta_c_high": delta_c, "cost_inr_low": low, "cost_inr_high": high,
            "unpriced_interventions": [], "trees": 2, "reflective_cells": 0}


CROSS_SECTION = {
    "source": "published_design", "reference": "test template", "right_of_way_m": 12.0,
    "right_of_way_source": "building_footprints",
    "bands": [{"kind": "carriageway", "offset_from_m": -3.0, "offset_to_m": 3.0, "plantable": False},
              {"kind": "tree_pit", "offset_from_m": 3.0, "offset_to_m": 4.0, "plantable": True}],
}


def optimization_result(**overrides):
    data = {
        "job_id": "job-1",
        "street": {"id": "test-street", "name": "Test Street"},
        "baseline_temp_c": 36.0,
        "optimized_temp_c_low": 34.8,
        "optimized_temp_c_high": 35.0,
        "temp_delta_c_low": -1.2,
        "temp_delta_c_high": -1.0,
        "cost_inr_low": 100.0,
        "cost_inr_high": 200.0,
        "unpriced_interventions": [],
        "model": {"rmse_holdout_c": 0.5, "rmse_mean_baseline_c": 2.0},
        "comparison": {"random": arm(-0.2, 90, 190), "greedy": arm(-0.5, 95, 195),
                       "design_guideline": arm(-0.8, 100, 200), "ga": arm(-1.0, 100, 200)},
        "interventions": [{"type": "tree", "cells": [[0, 0], [1, 1]]}],
        "design_grid": {
            "crs": "EPSG:32643", "origin_e_m": 374210.0, "origin_n_m": 2050880.0,
            "bearing_deg": 37.4, "cell_size_m": 2.0, "shape": [2, 2],
        },
        "cross_section": CROSS_SECTION,
        "plantable_mask": [[True, False], [True, False]],
        "before_lst_c": [[36.0, 36.1], [None, 36.2]],
        "after_lst_c_low": [[34.8, 36.1], [None, 35.0]],
        "after_lst_c_high": [[35.0, 36.1], [None, 35.2]],
        "resolution": {
            "measurement_resolution_m": 30, "calibration_resolution_m": 90, "design_resolution_m": 2,
            "output_kind": "model_output_at_design_resolution",
        },
        "provenance": [provenance(), provenance(product="land_cover")],
    }
    return {**data, **overrides}


def contract_models():
    return [
        obj for obj in vars(contracts).values()
        if isinstance(obj, type) and issubclass(obj, contracts.Contract) and obj is not contracts.Contract
    ]


def test_provenance_scene_ids_must_match_scene_count():
    with pytest.raises(ValidationError):
        Provenance(**provenance(scene_count=3))


def test_thermal_grid_invalid_cells_serialise_as_null():
    grid = ThermalGrid(**thermal_grid())
    assert '"lst_c":[[30.1,null,31.0],[29.5,30.0,null]]' in grid.model_dump_json()


def test_thermal_grid_rejects_shape_mismatch():
    with pytest.raises(ValidationError):
        ThermalGrid(**thermal_grid(shape=[2, 2]))


def test_thermal_grid_rejects_valid_pixel_count_that_disagrees_with_nulls():
    stats = {"min_c": 29.5, "max_c": 31.0, "mean_c": 30.15, "valid_pixels": 6}
    with pytest.raises(ValidationError):
        ThermalGrid(**thermal_grid(stats=stats))


def test_contracts_reject_removed_fields():
    with pytest.raises(ValidationError):
        ThermalGrid(**thermal_grid(valid_mask=[[True, False, True], [True, True, False]]))


def test_design_grid_accepts_exactly_the_cap_and_raises_above_it():
    base = {"crs": "EPSG:32643", "origin_e_m": 0.0, "origin_n_m": 0.0, "bearing_deg": 0.0, "cell_size_m": 2.0}
    DesignGrid(**base, shape=[80, 50])
    with pytest.raises(ValidationError, match="4000-cell cap"):
        DesignGrid(**base, shape=[4001, 1])


def test_optimization_result_round_trips():
    result = OptimizationResult(**optimization_result())
    assert OptimizationResult.model_validate_json(result.model_dump_json()) == result


def test_intervention_outside_design_grid_is_rejected():
    with pytest.raises(ValidationError, match="outside design grid"):
        OptimizationResult(**optimization_result(interventions=[{"type": "tree", "cells": [[2, 0]]}]))


def test_cost_range_must_be_ordered():
    with pytest.raises(ValidationError):
        ComparisonArm(**{**arm(-1.0, 300, 200)})


def test_temperature_band_must_be_ordered():
    with pytest.raises(ValidationError, match="temp_delta_c_low"):
        ComparisonArm(**{**arm(-1.0, 100, 200), "temp_delta_c_low": -0.5})


def test_cost_is_null_exactly_when_an_intervention_is_unpriced():
    ComparisonArm(**{**arm(-1.0, None, None), "unpriced_interventions": ["reflective_pavement"]})
    with pytest.raises(ValidationError, match="unpriced"):
        ComparisonArm(**{**arm(-1.0, 100, 200), "unpriced_interventions": ["reflective_pavement"]})
    with pytest.raises(ValidationError, match="unpriced"):
        ComparisonArm(**arm(-1.0, None, None))
    with pytest.raises(ValidationError, match="both be null"):
        ComparisonArm(**{**arm(-1.0, 100, None), "unpriced_interventions": ["reflective_pavement"]})


def test_websocket_message_discriminates_on_type():
    message = TypeAdapter(OptimizeMessage).validate_python({
        "type": "progress", "job_id": "job-1", "generation": 3, "generations_total": 400,
        "best_fitness_score": 1.2, "best_temp_delta_c_low": -0.9, "best_temp_delta_c_high": -0.8,
        "best_cost_inr_low": 100, "best_cost_inr_high": 200, "layout_preview": None,
    })
    assert isinstance(message, OptimizeProgress)
    assert message.layout_preview is None


def test_physical_fields_carry_unit_suffix():
    offenders = [
        f"{model.__name__}.{name}"
        for model in contract_models()
        for name, field in model.model_fields.items()
        if field.annotation in (int, float) and name not in DIMENSIONLESS and not UNIT_SUFFIX.search(name)
    ]
    assert offenders == []


def test_typescript_mirror_matches_pydantic_models():
    text = TS_CONTRACTS.read_text(encoding="utf-8").replace("\r\n", "\n")
    ts = {
        name: set(re.findall(r"^  (\w+)\??:", body, flags=re.M))
        for name, body in re.findall(r"export interface (\w+) \{\n(.*?)\n\}", text, flags=re.S)
    }
    py = {model.__name__: set(model.model_fields) for model in contract_models()}
    assert ts == py
