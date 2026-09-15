"""Street endpoints: list, geometry, thermal grid, and the street ranking (SPEC.md §7)."""

from typing import Literal

from fastapi import APIRouter, HTTPException

from app import pipeline
from app.contracts import StreetBasemap, StreetGeometry, StreetRanking, StreetSummary, ThermalGrid
from app.routers.errors import known_street

router = APIRouter()


@router.get("/api/streets", response_model=list[StreetSummary])
def list_streets() -> list[StreetSummary]:
    return [pipeline.street_summary(street_id) for street_id in pipeline.street_ids()]


@router.get("/api/ranking", response_model=StreetRanking)
def ranking() -> StreetRanking:
    try:
        return pipeline.street_ranking()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/street/{street_id}/geometry", response_model=StreetGeometry)
def geometry(street_id: str) -> StreetGeometry:
    with known_street(street_id):
        return pipeline.street_geometry(street_id)


@router.get("/api/street/{street_id}/basemap", response_model=StreetBasemap)
def basemap(street_id: str) -> StreetBasemap:
    with known_street(street_id):
        return pipeline.street_basemap(street_id)


@router.get("/api/street/{street_id}/thermal", response_model=ThermalGrid)
def thermal(street_id: str, scope: Literal["street", "window"] = "window") -> ThermalGrid:
    with known_street(street_id):
        return pipeline.thermal_grid(street_id, scope)
