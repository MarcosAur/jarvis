import logging
from celery.result import AsyncResult
from pipeline.celery_app import celery_app
from pipeline.domain.ports.job_dispatcher import (
    CeleryTaskStatus,
    JobDispatcher,
    WorkerHealthStatus,
)
from pipeline.tasks import execute_job_task, run_pipeline_task

logger = logging.getLogger(__name__)


class CeleryJobDispatcher(JobDispatcher):
    """Celery adapter implementing JobDispatcher."""

    def dispatch_job(self, job_id: int) -> str | None:
        result = execute_job_task.delay(job_id)
        return str(result.id) if result and result.id else None

    def dispatch_pipeline(self, project_id: int | None = None) -> str | None:
        result = run_pipeline_task.delay(project_id=project_id, trigger="celery")
        return str(result.id) if result and result.id else None

    def revoke_job(self, task_id: str) -> bool:
        try:
            celery_app.control.revoke(task_id, terminate=False)
            return True
        except Exception as exc:
            logger.warning("Não foi possível revogar a task Celery %s: %s", task_id, exc)
            return False

    def get_task_status(self, task_id: str) -> CeleryTaskStatus:
        try:
            async_res = AsyncResult(task_id, app=celery_app)
            state = str(async_res.state)
            detail = None
            if state == "FAILURE" and async_res.result:
                detail = str(async_res.result)
            return CeleryTaskStatus(task_id=task_id, state=state, detail=detail)
        except Exception as exc:
            return CeleryTaskStatus(
                task_id=task_id,
                state="UNAVAILABLE",
                detail=str(exc),
            )

    def get_worker_health(self) -> WorkerHealthStatus:
        try:
            # Verify broker connection quickly before inspect
            with celery_app.connection_for_read() as conn:
                conn.ensure_connection(max_retries=0, interval_start=0, interval_step=0, interval_max=0)
            inspector = celery_app.control.inspect(timeout=0.4)
            ping = inspector.ping() if inspector else None
            worker_names = sorted(ping.keys()) if isinstance(ping, dict) else []
            return WorkerHealthStatus(
                broker_available=True,
                workers_online=len(worker_names),
                worker_names=worker_names,
            )
        except Exception as exc:
            return WorkerHealthStatus(
                broker_available=False,
                workers_online=0,
                worker_names=[],
                error=str(exc),
            )
