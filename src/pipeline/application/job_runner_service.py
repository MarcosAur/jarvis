from datetime import datetime
from pathlib import Path
from pipeline.adapters.db.orm_models import utc_now
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.domain.entities import CliPromptRequest
from pipeline.domain.exceptions import EntityNotFoundError
from pipeline.domain.ports.uow import UnitOfWork
from pipeline.domain.provider_state import (
    is_cli_provider_enabled,
    is_project_provider_enabled,
)


class JobRunnerService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    def _update_process_status(self, job_id: int, process_status: str) -> None:
        with self.uow_factory() as uow:
            uow.jobs.update(job_id, process_status=process_status)
            uow.commit()

    def mark_failed(
        self,
        job_id: int,
        error: str,
        process_status: str = "Falha na execução",
    ) -> None:
        with self.uow_factory() as uow:
            job = uow.jobs.get_by_id(job_id)
            if not job:
                return
            if job.state in ("succeeded", "cancelled"):
                return
            uow.jobs.update(
                job_id,
                state="failed",
                process_status=process_status,
                error=error,
                finished_at=utc_now(),
            )
            uow.commit()

    def run_job(
        self,
        job_id: int,
        dry_run: bool = False,
        celery_task_id: str | None = None,
        only_if_pending: bool = False,
    ) -> dict:
        with self.uow_factory() as uow:
            job = uow.jobs.get_by_id(job_id)
            if not job:
                raise EntityNotFoundError(f"Job #{job_id} não encontrado.")

            if only_if_pending and job.state != "pending":
                return {
                    "success": False,
                    "skipped": True,
                    "job_id": job_id,
                    "reason": f"Job #{job_id} está em estado '{job.state}' e não será executado.",
                }

            card = uow.cards.get_by_id(job.card_id)
            project = uow.projects.get_by_id(job.project_id)
            agent = uow.agents.get_by_id(job.agent_id) if job.agent_id else None
            settings = uow.settings.get()

            # Mark running
            update_fields: dict = {
                "state": "running",
                "started_at": utc_now(),
                "process_status": "Iniciando execução no worker Celery" if celery_task_id else "Iniciando execução",
            }
            if celery_task_id is not None:
                update_fields["celery_task_id"] = celery_task_id
            uow.jobs.update(job.id, **update_fields)
            uow.commit()

        try:
            # Prepare execution
            provider_key = job.cli_provider_snapshot or (agent.cli_provider if agent else "agy")
            model_id = job.model_id_snapshot or (agent.model_id if agent else "gemini-4-argon-medium")
            if not model_id or model_id == "default":
                model_id = agent.model_id if agent and agent.model_id else "gemini-4-argon-medium"

            system_prompt = agent.prompt_markdown if agent else ""
            task_prompt = (
                f"# Demanda do Card\n"
                f"Título: {card.title}\n"
                f"Descrição:\n{card.body or '(Sem descrição informada)'}\n\n"
                f"Repositório local: {project.local_path}\n"
                f"Coluna Atual no Kanban: {card.column_name}\n"
                f"Próxima Coluna: {job.target_column_snapshot or 'Nenhuma'}\n\n"
                f"Por favor, analise a demanda acima e os arquivos do repositório local. "
                f"Forneça a sua resposta completa de acordo com o seu papel de agente."
            )
            working_dir = Path(project.local_path) if project and project.local_path and Path(project.local_path).is_dir() else Path.cwd()

            if dry_run:
                summary = (
                    f"[Simulação Dry-Run] Agente '{agent.name if agent else 'Desconhecido'}' "
                    f"({provider_key}/{model_id}) avaliou o card '{card.title}'. "
                    f"Próxima coluna configurada: '{job.target_column_snapshot or 'Nenhuma'}'."
                )
                with self.uow_factory() as uow:
                    uow.jobs.update(
                        job_id,
                        state="succeeded",
                        process_status="Concluído (simulação dry-run)",
                        output_summary=summary,
                        finished_at=utc_now(),
                    )
                    uow.commit()
                return {"success": True, "job_id": job_id, "summary": summary, "dry_run": True}

            # Live execution
            if not agent:
                error_msg = "Nenhum agente associado a este job para executar a IA."
                self.mark_failed(job_id, error_msg, process_status="Falha: agente não associado")
                return {"success": False, "job_id": job_id, "error": error_msg}

            if not is_cli_provider_enabled(provider_key, settings.provider_settings):
                error_msg = f"Provedor CLI '{provider_key}' está desativado nas Configurações."
                self.mark_failed(job_id, error_msg, process_status=f"Falha: CLI '{provider_key}' desativada")
                return {"success": False, "job_id": job_id, "error": error_msg}

            cli_provider = cli_registry.get_or_none(provider_key)
            if not cli_provider or not cli_provider.is_installed():
                error_msg = f"Provedor CLI '{provider_key}' não está instalado no sistema."
                self.mark_failed(job_id, error_msg, process_status=f"Falha: CLI '{provider_key}' não instalada")
                return {"success": False, "job_id": job_id, "error": error_msg}

            self._update_process_status(
                job_id,
                f"Executando agente '{agent.name}' ({provider_key}/{model_id})",
            )

            req = CliPromptRequest(
                model_id=model_id,
                system_prompt_markdown=system_prompt,
                task_prompt=task_prompt,
                working_dir=working_dir,
            )
            res = cli_provider.execute_prompt(req)

            if res.success:
                warnings = []
                project_provider_key = project.project_provider if project and project.project_provider else None
                if job.target_column_snapshot and project_provider_key:
                    if not is_project_provider_enabled(project_provider_key, settings.provider_settings):
                        warnings.append(
                            f"Provedor '{project_provider_key}' desativado; movimentação remota ignorada."
                        )
                    else:
                        p_provider = project_registry.get_or_none(project_provider_key)
                        if p_provider:
                            self._update_process_status(
                                job_id,
                                f"Atualizando card no provedor ({project_provider_key})",
                            )
                            try:
                                p_provider.add_comment(
                                    project.project_key,
                                    card.remote_id,
                                    f"🤖 **Agente {agent.name}** ({provider_key}/{model_id}):\n\n{res.output_text}",
                                    settings.provider_settings,
                                )
                            except Exception as e:
                                warnings.append(f"Falha ao comentar no card: {e}")
                            try:
                                p_provider.move_card(
                                    project.project_key,
                                    card.remote_id,
                                    job.target_column_snapshot,
                                    settings.provider_settings,
                                )
                                with self.uow_factory() as uow:
                                    uow.cards.update(card.id, column_name=job.target_column_snapshot)
                                    uow.events.create(
                                        card_id=card.id,
                                        event_type="column_changed",
                                        from_column=card.column_name,
                                        to_column=job.target_column_snapshot,
                                    )
                                    uow.commit()
                            except Exception as e:
                                warnings.append(f"Falha ao mover o card: {e}")

                with self.uow_factory() as uow:
                    final_status = "Concluído com avisos no quadro" if warnings else "Concluído com sucesso"
                    uow.jobs.update(
                        job_id,
                        state="succeeded",
                        process_status=final_status,
                        output_summary=res.output_text,
                        error=" | ".join(warnings) if warnings else None,
                        finished_at=utc_now(),
                    )
                    uow.commit()
                return {"success": True, "job_id": job_id, "output": res.output_text}
            else:
                error_msg = res.error_message or "Erro desconhecido na execução da CLI"
                proc_status = (
                    "Timeout do Celery excedido"
                    if "SoftTimeLimitExceeded" in error_msg
                    else "Falha na execução do agente"
                )
                self.mark_failed(job_id, error_msg, process_status=proc_status)
                return {"success": False, "job_id": job_id, "error": res.error_message}
        except Exception as exc:
            proc_status = (
                "Timeout do Celery excedido"
                if type(exc).__name__ == "SoftTimeLimitExceeded"
                else "Erro inesperado no worker Celery"
            )
            self.mark_failed(job_id, str(exc), process_status=proc_status)
            raise

    def run_all_pending(self, project_id: int | None = None, limit: int = 50, dry_run: bool = True) -> list[dict]:
        with self.uow_factory() as uow:
            pending_jobs = uow.jobs.list_all(project_id=project_id, state="pending", limit=limit)
            job_ids = [j.id for j in pending_jobs]

        results = []
        for j_id in job_ids:
            res = self.run_job(j_id, dry_run=dry_run)
            results.append(res)
        return results

