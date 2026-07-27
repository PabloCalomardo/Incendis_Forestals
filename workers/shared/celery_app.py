from celery import Celery

from shared.config import get_worker_settings


def create_celery_app(name: str, default_queue: str) -> Celery:
    settings = get_worker_settings()
    app = Celery(name, broker=settings.celery_broker_url, backend=settings.celery_result_backend)
    app.conf.update(
        task_default_queue=default_queue,
        task_routes={f"{name}.*": {"queue": default_queue}},
        task_always_eager=settings.task_always_eager,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "run-firms-every-15-minutes": {
                "task": "ingestion.run_firms",
                "schedule": 900.0,
            },
            "run-aemet-every-60-minutes": {
                "task": "ingestion.run_aemet",
                "schedule": 3600.0,
            },
            "run-ign-transport-daily": {
                "task": "ingestion.run_ign_transport",
                "schedule": 86400.0,
            },
            "run-osm-roads-daily": {
                "task": "ingestion.run_osm_roads",
                "schedule": 86400.0,
            },
            "run-nap-datex-traffic-every-5-minutes": {
                "task": "ingestion.run_datex_traffic",
                "schedule": 300.0,
            },
            "enrich-nap-datex-roads-every-minute": {
                "task": "ingestion.enrich_datex_roads",
                "schedule": 60.0,
            },
            "run-proteccio-civil-plans-every-10-minutes": {
                "task": "ingestion.run_proteccio_civil_plans",
                "schedule": 600.0,
            },
        }
        if name == "ingestion"
        else {},
    )
    return app
