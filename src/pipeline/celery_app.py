from celery import Celery
from celery.signals import beat_init, worker_ready
from pipeline.config import config

celery_app = Celery(
    "pipeline",
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND,
    include=["pipeline.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=config.celery_soft_time_limit,
    task_time_limit=config.celery_time_limit,
    task_always_eager=config.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
        "max_retries": 1,
        "retry_on_timeout": False,
    },
    result_backend_transport_options={
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
        "retry_on_timeout": False,
    },
    redis_socket_timeout=2,
    redis_socket_connect_timeout=2,
    redis_retry_on_timeout=False,
    result_expires=86400,
    beat_schedule={
        "run-pipeline-periodic": {
            "task": "pipeline.tasks.run_pipeline",
            "schedule": float(max(config.CELERY_PIPELINE_INTERVAL_SECONDS, 5)),
        },
    },
)


@worker_ready.connect
@beat_init.connect
def _init_database_on_celery_start(**_kwargs) -> None:
    from pipeline.adapters.db.seed import seed_database

    seed_database()
