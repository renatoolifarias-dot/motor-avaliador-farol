"""Celery app config (placeholder — tasks reais virão nos próximos sprints)."""
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "farol_avaliador",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bahia",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=50,
)


@celery_app.task
def ping():
    """Sanity check da queue."""
    return "pong"
