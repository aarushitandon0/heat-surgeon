"""Street endpoints: list, geometry, thermal grid (SPEC.md §7)."""

from typing import Literal

from fastapi import APIRouter

from app import pipeline
from app.contracts import StreetGeometry, StreetSummary, ThermalGrid
from app.routers.errors import known_street

router = APIRouter()


@router.get("/api/streets", response_model=list[StreetSummary])
def list_streets() -> list[StreetSummary]:
    return [pipeline.street_summary(street_id) for street_id in pipeline.street_ids()]


@router.get("/api/street/{street_id}/geometry", response_model=StreetGeometry)
def geometry(street_id: str) -> StreetGeometry:
    with known_street(street_id):
        return pipeline.street_geometry(street_id)


@router.get("/api/street/{street_id}/thermal", response_model=ThermalGrid)
def thermal(street_id: str, scope: Literal["street", "window"] = "window") -> ThermalGrid:
    with known_street(street_id):
        return pipeline.thermal_grid(street_id, scope)
