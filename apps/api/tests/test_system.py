from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-correlation-id" in response.headers


def test_version_returns_project_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["name"] == "wildfire-intelligence-platform"


def test_internal_ingestion_status_is_not_public() -> None:
    client = TestClient(create_app())

    response = client.get("/internal/ingestion/firms/status")

    assert response.status_code == 404
