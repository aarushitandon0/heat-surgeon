"""Neighbourhood calibration endpoint: POST /api/street/{id}/calibrate (SPEC.md §7)."""

from fastapi import APIRouter

from app import pipeline
from app.contracts import CalibrationRequest, CalibrationResult
from app.routers.errors import known_street

router = APIRouter()


@router.post("/api/street/{street_id}/calibrate", response_model=CalibrationResult)
def calibrate(street_id: str, request: CalibrationRequest | None = None) -> CalibrationResult:
    with known_street(street_id):
        return pipeline.calibration(street_id, request or CalibrationRequest())
