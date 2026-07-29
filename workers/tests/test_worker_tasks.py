from geospatial.worker import ping as geospatial_ping
from geospatial.worker import run_quality_pipeline
from ingestion.worker import ping as ingestion_ping
from ingestion.worker import run_emergency_osint
from ingestion.worker import run_aemet, run_firms, run_ign_transport, run_osm_roads
from predictions.worker import ping as predictions_ping


def test_ingestion_ping_task() -> None:
    assert ingestion_ping.run() == {"worker": "ingestion", "status": "ok"}


def test_geospatial_ping_task() -> None:
    assert geospatial_ping.run() == {"worker": "geospatial", "status": "ok"}


def test_predictions_ping_task() -> None:
    assert predictions_ping.run() == {"worker": "predictions", "status": "ok"}


def test_ingestion_firms_task_registered() -> None:
    assert run_firms.name == "ingestion.run_firms"


def test_phase4_ingestion_tasks_registered() -> None:
    assert run_aemet.name == "ingestion.run_aemet"
    assert run_ign_transport.name == "ingestion.run_ign_transport"
    assert run_osm_roads.name == "ingestion.run_osm_roads"
    assert run_emergency_osint.name == "ingestion.run_emergency_osint"


def test_quality_pipeline_task_registered() -> None:
    assert run_quality_pipeline.name == "geospatial.run_quality_pipeline"
