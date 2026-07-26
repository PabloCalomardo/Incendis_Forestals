from shared.celery_app import create_celery_app

celery_app = create_celery_app("ingestion", "ingestion")


@celery_app.task(name="ingestion.ping")  # type: ignore[misc]
def ping() -> dict[str, str]:
    return {"worker": "ingestion", "status": "ok"}
