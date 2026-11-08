from datetime import datetime
from pathlib import Path
from pipeline.adapters.db.orm_models import utc_now
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.domain.entities import CliPromptRequest
from pipeline.domain.exceptions import EntityNotFoundError
from pipeline.domain.ports.uow import UnitOfWork


class JobRunnerService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    def run_job(self, job_id: int, dry_run: bool = True) -> dict:
        with self.uow_factory() as uow:
            job = uow.jobs.get_by_id(job_id)
            if not job:
                raise EntityNotFoundError(f"Job #{job_id} não encontrado.")

            card = uow.cards.get_by_id(job.card_id)
            project = uow.projects.get_by_id(job.project_id)
            agent = uow.agents.get_by_id(job.agent_id) if job.agent_id else None
            settings = uow.settings.get()

            # Mark running
            uow.jobs.update(job.id, state="running", started_at=utc_now())
            uow.commit()

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
                    output_summary=summary,
                    finished_at=utc_now(),
                )
                uow.commit()
            return {"success": True, "job_id": job_id, "summary": summary, "dry_run": True}

        # Live execution
        if not agent:
            error_msg = "Nenhum agente associado a este job para executar a IA."
            with self.uow_factory() as uow:
                uow.jobs.update(
                    job_id,
                    state="failed",
                    error=error_msg,
                    finished_at=utc_now(),
                )
                uow.commit()
            return {"success": False, "job_id": job_id, "error": error_msg}

        cli_provider = cli_registry.get_or_none(provider_key)
        if not cli_provider or not cli_provider.is_installed():
            error_msg = f"Provedor CLI '{provider_key}' não está instalado no sistema."
            with self.uow_factory() as uow:
                uow.jobs.update(
                    job_id,
                    state="failed",
                    error=error_msg,
                    finished_at=utc_now(),
                )
                uow.commit()
            return {"success": False, "job_id": job_id, "error": error_msg}

        req = CliPromptRequest(
            model_id=model_id,
            system_prompt_markdown=system_prompt,
            task_prompt=task_prompt,
            working_dir=working_dir,
        )
        res = cli_provider.execute_prompt(req)

        with self.uow_factory() as uow:
            if res.success:
                uow.jobs.update(
                    job_id,
                    state="succeeded",
                    output_summary=res.output_text,
                    finished_at=utc_now(),
                )

                # Move card if target column snapshot is defined and external board is accessible
                if job.target_column_snapshot and settings.active_project_provider:
                    p_provider = project_registry.get_or_none(settings.active_project_provider)
                    if p_provider:
                        warnings = []
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
                            uow.cards.update(card.id, column_name=job.target_column_snapshot)
                            uow.events.create(
                                card_id=card.id,
                                event_type="column_changed",
                                from_column=card.column_name,
                                to_column=job.target_column_snapshot,
                            )
                        except Exception as e:
                            warnings.append(f"Falha ao mover o card: {e}")
                        if warnings:
                            uow.jobs.update(job_id, error=" | ".join(warnings))
                uow.commit()
                return {"success": True, "job_id": job_id, "output": res.output_text}
            else:
                uow.jobs.update(
                    job_id,
                    state="failed",
                    error=res.error_message or "Erro desconhecido na execução da CLI",
                    finished_at=utc_now(),
                )
                uow.commit()
                return {"success": False, "job_id": job_id, "error": res.error_message}

    def run_all_pending(self, project_id: int | None = None, limit: int = 50, dry_run: bool = True) -> list[dict]:
        with self.uow_factory() as uow:
            pending_jobs = uow.jobs.list_all(project_id=project_id, state="pending", limit=limit)
            job_ids = [j.id for j in pending_jobs]

        results = []
        for j_id in job_ids:
            res = self.run_job(j_id, dry_run=dry_run)
            results.append(res)
        return results

