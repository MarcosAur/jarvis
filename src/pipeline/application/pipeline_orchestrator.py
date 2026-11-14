from datetime import datetime
import logging
from typing import Any
from pipeline.adapters.db.orm_models import PipelineRun, utc_now
from pipeline.application.sync_service import SyncService
from pipeline.bootstrap import project_registry
from pipeline.domain.exceptions import BoardError, EntityNotFoundError
from pipeline.domain.ports.job_dispatcher import JobDispatcher

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(
        self,
        uow_factory,
        sync_service: SyncService | None = None,
        job_dispatcher: JobDispatcher | None = None,
    ):
        self.uow_factory = uow_factory
        self.sync_service = sync_service or SyncService()
        self.job_dispatcher = job_dispatcher

    def run_for_project(self, project_id: int, trigger: str = "web_project") -> PipelineRun:
        with self.uow_factory() as uow:
            project = uow.projects.get_by_id(project_id)
            if not project:
                raise EntityNotFoundError(f"Projeto com id {project_id} não encontrado.")

            project_key = project.project_key
            project_name = project.name
            project_db_id = project.id

            settings = uow.settings.get()
            provider_key = settings.active_project_provider
            default_cli = settings.default_cli_provider
            provider_settings = dict(settings.provider_settings or {})

            p_provider = project_registry.get_or_none(provider_key)
            if not p_provider:
                raise BoardError(f"Provedor de projeto '{provider_key}' não está registrado.")

            # Create PipelineRun record
            run = uow.runs.create(
                trigger=trigger,
                project_provider_used=provider_key,
                project_id=project_db_id,
                cli_provider_used=default_cli,
            )
            uow.commit()
            run_id = run.id

        cards_synced_count = 0
        jobs_created_count = 0
        error_msg: str | None = None
        status = "ok"
        jobs_to_dispatch: list[int] = []
        tasks_to_revoke: list[str] = []

        try:
            # 1. Fetch cards from external provider
            remote_cards = p_provider.fetch_cards(project_key, provider_settings)
            cards_synced_count = len(remote_cards)

            with self.uow_factory() as uow:
                # 2. Sync cards and generate diff events
                self.sync_service.sync_cards(project_db_id, remote_cards, uow)

                # 3. Fetch active flow columns with assigned agent
                flow_columns = uow.columns.list_all(active_only=True)
                col_map = {c.column_name.strip().lower(): c for c in flow_columns}

                # 4. For each active card in project
                active_cards = uow.cards.list_by_project(project_db_id, include_removed=False)
                active_card_ids = set()

                for card in active_cards:
                    active_card_ids.add(card.id)
                    col_key = card.column_name.strip().lower()
                    flow_col = col_map.get(col_key)

                    # If this column has an agent assigned, check for pending/running job
                    if flow_col and flow_col.agent_id:
                        agent = uow.agents.get_by_id(flow_col.agent_id)
                        existing_job = uow.jobs.get_active_job_for_card(card.id, flow_col.id)

                        if not existing_job:
                            # Create new pending Job
                            new_job = uow.jobs.create(
                                project_id=project_db_id,
                                card_id=card.id,
                                flow_column_id=flow_col.id,
                                agent_id=agent.id if agent else None,
                                cli_provider_snapshot=agent.cli_provider if agent else None,
                                model_id_snapshot=agent.model_id if agent else None,
                                target_column_snapshot=flow_col.next_column_name,
                                state="pending",
                                process_status="Aguardando envio ao Celery",
                            )
                            jobs_to_dispatch.append(new_job.id)
                            jobs_created_count += 1

                # 5. Cancel pending jobs if card moved out of the column, and collect orphaned pending jobs
                pending_jobs = uow.jobs.list_all(project_id=project_db_id, state="pending")
                for job in pending_jobs:
                    job_col = uow.columns.get_by_id(job.flow_column_id)
                    job_card = uow.cards.get_by_id(job.card_id)
                    if not job_card or job_card.removed or (job_col and job_card.column_name.strip().lower() != job_col.column_name.strip().lower()):
                        uow.jobs.update(
                            job.id,
                            state="cancelled",
                            process_status="Cancelado (card movido da coluna)",
                            finished_at=utc_now(),
                        )
                        if job.celery_task_id:
                            tasks_to_revoke.append(job.celery_task_id)
                    elif not job.celery_task_id and job.id not in jobs_to_dispatch:
                        jobs_to_dispatch.append(job.id)

                # Update project last run
                uow.projects.update(project_db_id, last_run_at=utc_now())
                uow.commit()

            # 6. Dispatch pending jobs and revoke cancelled tasks via Celery after DB commit
            if self.job_dispatcher is not None:
                for task_id in tasks_to_revoke:
                    try:
                        self.job_dispatcher.revoke_job(task_id)
                    except Exception as exc:
                        logger.warning("Falha ao revogar task Celery %s: %s", task_id, exc)

                for job_id in jobs_to_dispatch:
                    try:
                        task_id = self.job_dispatcher.dispatch_job(job_id)
                        with self.uow_factory() as uow:
                            current_job = uow.jobs.get_by_id(job_id)
                            if current_job:
                                updates: dict[str, Any] = {}
                                if task_id and not current_job.celery_task_id:
                                    updates["celery_task_id"] = task_id
                                if current_job.state == "pending":
                                    updates["process_status"] = (
                                        "Na fila do Celery" if task_id else "Pendente (aguardando envio ao Celery)"
                                    )
                                if updates:
                                    uow.jobs.update(job_id, **updates)
                                    uow.commit()
                    except Exception as exc:
                        logger.warning("Falha ao enviar Job #%s para o Celery: %s", job_id, exc)
                        with self.uow_factory() as uow:
                            current_job = uow.jobs.get_by_id(job_id)
                            if current_job and current_job.state == "pending":
                                uow.jobs.update(
                                    job_id,
                                    process_status="Pendente (broker Celery indisponível)",
                                )
                                uow.commit()

        except Exception as e:
            logger.exception("Erro ao rodar pipeline para o projeto %s: %s", project_name, e)
            status = "error"
            error_msg = str(e)

        # Finalize run
        with self.uow_factory() as uow:
            run = uow.runs.update(
                run_id,
                cards_synced=cards_synced_count,
                jobs_created=jobs_created_count,
                status=status,
                error=error_msg,
                finished_at=utc_now(),
            )
            uow.commit()

        return run

    def run_all_active(self, trigger: str = "web_all") -> list[PipelineRun]:
        with self.uow_factory() as uow:
            projects = uow.projects.list_all(active_only=True)

        runs = []
        for p in projects:
            run = self.run_for_project(p.id, trigger=trigger)
            runs.append(run)
        return runs
