"""The app imports and serves its OpenAPI schema."""

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_is_served():
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
