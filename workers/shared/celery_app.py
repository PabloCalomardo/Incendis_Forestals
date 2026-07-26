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
    )
    return app
