import logging
import random
from celery.exceptions import Retry, SoftTimeLimitExceeded
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.adapters.redis_concurrency_limiter import get_concurrency_limiter
from pipeline.application.job_runner_service import JobRunnerService
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.application.sync_service import SyncService
from pipeline.celery_app import celery_app
from pipeline.config import config

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="pipeline.tasks.execute_job",
    soft_time_limit=config.celery_soft_time_limit,
    time_limit=config.celery_time_limit,
)
def execute_job_task(self, job_id: int) -> dict:
    """Execute a single pipeline Job inside a Celery worker, respecting per-(agent, project) limits."""
    runner = JobRunnerService(SqlAlchemyUnitOfWork)
    task_id = getattr(self.request, "id", None)
    limiter = None
    slot_scope: tuple[int, int] | None = None

    try:
        with SqlAlchemyUnitOfWork() as uow:
            job = uow.jobs.get_by_id(job_id)
            if job and job.state == "pending" and job.agent_id is not None:
                agent = uow.agents.get_by_id(job.agent_id)
                max_parallel = max(int(agent.max_parallel_executions), 1) if agent else 1
                agent_id = job.agent_id
                project_id = job.project_id

                limiter = get_concurrency_limiter(always_eager=bool(celery_app.conf.task_always_eager))
                acq = limiter.try_acquire(
                    agent_id=agent_id,
                    project_id=project_id,
                    job_id=job_id,
                    max_parallel=max_parallel,
                    ttl_seconds=config.celery_time_limit + 60,
                )
                if not acq.acquired:
                    uow.jobs.update(
                        job_id,
                        process_status=(
                            f"Aguardando vaga paralela do agente neste projeto "
                            f"({acq.active_count}/{acq.max_parallel} em execução)"
                        ),
                    )
                    uow.commit()
                    countdown = config.CELERY_AGENT_SLOT_RETRY_SECONDS + random.randint(0, 4)
                    logger.info(
                        "Job #%s aguardando slot para agente #%s no projeto #%s (%s/%s). Retry em %ss.",
                        job_id,
                        agent_id,
                        project_id,
                        acq.active_count,
                        acq.max_parallel,
                        countdown,
                    )
                    raise self.retry(countdown=countdown, max_retries=None)

                slot_scope = (agent_id, project_id)

        return runner.run_job(
            job_id,
            dry_run=False,
            celery_task_id=task_id,
            only_if_pending=True,
        )
    except Retry:
        raise
    except SoftTimeLimitExceeded:
        timeout_msg = (
            f"A task do Celery excedeu o limite suave de {config.celery_soft_time_limit}s "
            f"(timeout do agente: {config.CLI_TIMEOUT_SECONDS}s + margem operacional)."
        )
        logger.error("Timeout do Celery no Job #%s: %s", job_id, timeout_msg)
        runner.mark_failed(
            job_id,
            error=timeout_msg,
            process_status="Timeout do Celery excedido",
        )
        raise
    except Exception as exc:
        logger.exception("Erro inesperado ao executar Job #%s no Celery: %s", job_id, exc)
        runner.mark_failed(
            job_id,
            error=str(exc),
            process_status="Erro inesperado no worker Celery",
        )
        raise
    finally:
        if limiter is not None and slot_scope is not None:
            limiter.release(slot_scope[0], slot_scope[1], job_id)


@celery_app.task(bind=True, name="pipeline.tasks.run_pipeline")
def run_pipeline_task(self, project_id: int | None = None, trigger: str = "celery_beat") -> dict:
    """Run the pipeline board sync and enqueue pending jobs to Celery."""
    from pipeline.adapters.celery_dispatcher import CeleryJobDispatcher

    dispatcher = CeleryJobDispatcher()
    orchestrator = PipelineOrchestrator(
        SqlAlchemyUnitOfWork,
        SyncService(),
        job_dispatcher=dispatcher,
    )

    if project_id is not None:
        run = orchestrator.run_for_project(project_id, trigger=trigger)
        return {
            "mode": "single_project",
            "project_id": project_id,
            "run_id": run.id,
            "status": run.status,
            "cards_synced": run.cards_synced,
            "jobs_created": run.jobs_created,
            "error": run.error,
        }

    runs = orchestrator.run_all_active(trigger=trigger)
    return {
        "mode": "all_active",
        "projects_processed": len(runs),
        "cards_synced": sum(r.cards_synced for r in runs),
        "jobs_created": sum(r.jobs_created for r in runs),
    }
