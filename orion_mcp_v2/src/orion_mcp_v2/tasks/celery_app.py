from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from orion_mcp_v2.config.settings import get_settings


def make_celery() -> Celery:
    s = get_settings()
    app = Celery(
        "orion_v2",
        broker=s.celery_broker_url,
        backend=s.celery_result_backend,
    )
    app.conf.task_default_queue = "orion_v2"
    app.conf.timezone = "UTC"
    app.conf.beat_schedule = {
        "orion-v2-nightly-consolidate": {
            "task": "orion_v2.consolidate_all_users",
            "schedule": crontab(hour=s.consolidation_hour, minute=s.consolidation_minute),
        },
    }
    return app


celery_app = make_celery()


def register_tasks() -> None:
    import orion_mcp_v2.tasks.consolidate_tasks  # noqa: F401


register_tasks()
