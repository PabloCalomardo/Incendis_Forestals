from shared.celery_app import create_celery_app

celery_app = create_celery_app("geospatial", "geospatial")


@celery_app.task(name="geospatial.ping")  # type: ignore[misc]
def ping() -> dict[str, str]:
    return {"worker": "geospatial", "status": "ok"}
