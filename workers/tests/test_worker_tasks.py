from geospatial.worker import ping as geospatial_ping
from ingestion.worker import ping as ingestion_ping
from predictions.worker import ping as predictions_ping


def test_ingestion_ping_task() -> None:
    assert ingestion_ping.run() == {"worker": "ingestion", "status": "ok"}


def test_geospatial_ping_task() -> None:
    assert geospatial_ping.run() == {"worker": "geospatial", "status": "ok"}


def test_predictions_ping_task() -> None:
    assert predictions_ping.run() == {"worker": "predictions", "status": "ok"}
