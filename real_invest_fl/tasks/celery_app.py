"""Celery application with Redis broker."""
from celery import Celery
from config.settings import settings

celery_app = Celery(
    "real_invest_fl",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "real_invest_fl.tasks.ingest_tasks",
        "real_invest_fl.tasks.listing_tasks",
        "real_invest_fl.tasks.notification_tasks",
    ],
)

celery_app.conf.timezone = "UTC"
