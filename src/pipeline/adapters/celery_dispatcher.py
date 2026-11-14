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
            inspector = celery_app.control.inspect(timeout=0.5)
            ping = inspector.ping() if inspector else None
            worker_names = sorted(ping.keys()) if isinstance(ping, dict) else []
            nodes_online = len(worker_names)
            total_concurrency = 0
            active_tasks_count = 0

            if worker_names and inspector:
                stats = inspector.stats()
                if isinstance(stats, dict) and stats:
                    for name in worker_names:
                        node_stats = stats.get(name) or {}
                        pool_info = node_stats.get("pool") if isinstance(node_stats, dict) else {}
                        concurrency = pool_info.get("max-concurrency") if isinstance(pool_info, dict) else None
                        total_concurrency += max(int(concurrency), 1) if isinstance(concurrency, int) else 1
                else:
                    total_concurrency = nodes_online

                active_map = inspector.active()
                if isinstance(active_map, dict):
                    for task_list in active_map.values():
                        if isinstance(task_list, list):
                            active_tasks_count += len(task_list)

            return WorkerHealthStatus(
                broker_available=True,
                workers_online=total_concurrency,
                worker_names=worker_names,
                nodes_online=nodes_online,
                active_tasks_count=active_tasks_count,
            )
        except Exception as exc:
            return WorkerHealthStatus(
                broker_available=False,
                workers_online=0,
                worker_names=[],
                error=str(exc),
            )
