from shared.celery_app import create_celery_app

celery_app = create_celery_app("predictions", "predictions")


@celery_app.task(name="predictions.ping")  # type: ignore[misc]
def ping() -> dict[str, str]:
    return {"worker": "predictions", "status": "ok"}
