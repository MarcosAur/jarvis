from datetime import datetime, timezone
from typing import Any
from sqlmodel import Session, select, desc
from pipeline.adapters.db.orm_models import (
    Agent,
    AppSettings,
    Card,
    CardEvent,
    CliModel,
    FlowColumn,
    Job,
    PipelineRun,
    Project,
    utc_now,
)
from pipeline.domain.exceptions import EntityNotFoundError


class SqlSettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self) -> AppSettings:
        settings = self.session.exec(select(AppSettings).where(AppSettings.id == 1)).first()
        if not settings:
            settings = AppSettings(
                id=1,
                default_cli_provider="agy",
                active_project_provider="github",
                provider_settings={},
                updated_at=utc_now(),
            )
            self.session.add(settings)
            self.session.flush()
        return settings

    def update(
        self,
        default_cli_provider: str | None = None,
        active_project_provider: str | None = None,
        provider_settings: dict[str, Any] | None = None,
    ) -> AppSettings:
        settings = self.get()
        if default_cli_provider is not None:
            settings.default_cli_provider = default_cli_provider
        if active_project_provider is not None:
            settings.active_project_provider = active_project_provider
        if provider_settings is not None:
            settings.provider_settings = provider_settings
        settings.updated_at = utc_now()
        self.session.add(settings)
        self.session.flush()
        return settings


class SqlAgentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, agent_id: int) -> Agent | None:
        return self.session.exec(select(Agent).where(Agent.id == agent_id)).first()

    def get_by_name(self, name: str) -> Agent | None:
        return self.session.exec(select(Agent).where(Agent.name == name)).first()

    def list_all(self, active_only: bool = False) -> list[Agent]:
        stmt = select(Agent)
        if active_only:
            stmt = stmt.where(Agent.active == True)  # noqa: E712
        stmt = stmt.order_by(Agent.name)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        name: str,
        cli_provider: str,
        model_id: str,
        prompt_markdown: str,
        active: bool = True,
        max_parallel_executions: int = 1,
    ) -> Agent:
        agent = Agent(
            name=name,
            cli_provider=cli_provider,
            model_id=model_id,
            prompt_markdown=prompt_markdown,
            max_parallel_executions=max(int(max_parallel_executions), 1),
            active=active,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(agent)
        self.session.flush()
        return agent

    def update(self, agent_id: int, **kwargs: Any) -> Agent:
        agent = self.get_by_id(agent_id)
        if not agent:
            raise EntityNotFoundError(f"Agent with id {agent_id} not found.")
        for k, v in kwargs.items():
            if hasattr(agent, k):
                setattr(agent, k, v)
        agent.updated_at = utc_now()
        self.session.add(agent)
        self.session.flush()
        return agent

    def delete(self, agent_id: int) -> bool:
        agent = self.get_by_id(agent_id)
        if not agent:
            return False
        self.session.delete(agent)
        self.session.flush()
        return True


class SqlProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, project_id: int) -> Project | None:
        return self.session.exec(select(Project).where(Project.id == project_id)).first()

    def get_by_key(self, project_key: str) -> Project | None:
        return self.session.exec(select(Project).where(Project.project_key == project_key)).first()

    def list_all(self, active_only: bool = False) -> list[Project]:
        stmt = select(Project)
        if active_only:
            stmt = stmt.where(Project.active == True)  # noqa: E712
        stmt = stmt.order_by(Project.name)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        project_key: str,
        name: str,
        local_path: str,
        active: bool = True,
        project_provider: str = "github",
    ) -> Project:
        project = Project(
            project_key=project_key,
            project_provider=(project_provider or "github").strip(),
            name=name,
            local_path=local_path,
            active=active,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(project)
        self.session.flush()
        return project

    def update(self, project_id: int, **kwargs: Any) -> Project:
        project = self.get_by_id(project_id)
        if not project:
            raise EntityNotFoundError(f"Project with id {project_id} not found.")
        for k, v in kwargs.items():
            if hasattr(project, k):
                setattr(project, k, v)
        project.updated_at = utc_now()
        self.session.add(project)
        self.session.flush()
        return project

    def delete(self, project_id: int) -> bool:
        project = self.get_by_id(project_id)
        if not project:
            return False
        self.session.delete(project)
        self.session.flush()
        return True


class SqlFlowColumnRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, column_id: int) -> FlowColumn | None:
        return self.session.exec(select(FlowColumn).where(FlowColumn.id == column_id)).first()

    def get_by_identifier(self, identifier: str) -> FlowColumn | None:
        return self.session.exec(select(FlowColumn).where(FlowColumn.identifier == identifier)).first()

    def get_by_column_name(self, column_name: str) -> FlowColumn | None:
        return self.session.exec(select(FlowColumn).where(FlowColumn.column_name == column_name)).first()

    def list_all(self, active_only: bool = False) -> list[FlowColumn]:
        stmt = select(FlowColumn)
        if active_only:
            stmt = stmt.where(FlowColumn.active == True)  # noqa: E712
        stmt = stmt.order_by(FlowColumn.order_index)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        identifier: str,
        column_name: str,
        agent_id: int | None = None,
        next_column_name: str | None = None,
        order_index: int = 0,
        active: bool = True,
    ) -> FlowColumn:
        col = FlowColumn(
            identifier=identifier,
            column_name=column_name,
            agent_id=agent_id,
            next_column_name=next_column_name,
            order_index=order_index,
            active=active,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(col)
        self.session.flush()
        return col

    def update(self, column_id: int, **kwargs: Any) -> FlowColumn:
        col = self.get_by_id(column_id)
        if not col:
            raise EntityNotFoundError(f"FlowColumn with id {column_id} not found.")
        for k, v in kwargs.items():
            if hasattr(col, k):
                setattr(col, k, v)
        col.updated_at = utc_now()
        self.session.add(col)
        self.session.flush()
        return col

    def delete(self, column_id: int) -> bool:
        col = self.get_by_id(column_id)
        if not col:
            return False
        self.session.delete(col)
        self.session.flush()
        return True


class SqlJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, job_id: int) -> Job | None:
        return self.session.exec(select(Job).where(Job.id == job_id)).first()

    def list_all(
        self,
        project_id: int | None = None,
        card_id: int | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        stmt = select(Job)
        if project_id is not None:
            stmt = stmt.where(Job.project_id == project_id)
        if card_id is not None:
            stmt = stmt.where(Job.card_id == card_id)
        if state is not None:
            stmt = stmt.where(Job.state == state)
        stmt = stmt.order_by(desc(Job.created_at)).limit(limit)
        return list(self.session.exec(stmt).all())

    def get_active_job_for_card(self, card_id: int, flow_column_id: int) -> Job | None:
        stmt = select(Job).where(
            Job.card_id == card_id,
            Job.flow_column_id == flow_column_id,
            Job.state.in_(["pending", "running"]),  # type: ignore
        )
        return self.session.exec(stmt).first()

    def create(
        self,
        project_id: int,
        card_id: int,
        flow_column_id: int,
        agent_id: int | None,
        cli_provider_snapshot: str | None,
        model_id_snapshot: str | None,
        target_column_snapshot: str | None,
        state: str = "pending",
        iteration: int = 1,
        celery_task_id: str | None = None,
        process_status: str | None = None,
    ) -> Job:
        default_status = process_status if process_status is not None else (
            "Aguardando envio ao Celery" if state == "pending" else None
        )
        job = Job(
            project_id=project_id,
            card_id=card_id,
            flow_column_id=flow_column_id,
            agent_id=agent_id,
            cli_provider_snapshot=cli_provider_snapshot,
            model_id_snapshot=model_id_snapshot,
            target_column_snapshot=target_column_snapshot,
            state=state,
            iteration=iteration,
            celery_task_id=celery_task_id,
            process_status=default_status,
            created_at=utc_now(),
        )
        self.session.add(job)
        self.session.flush()
        return job

    def update(self, job_id: int, **kwargs: Any) -> Job:
        job = self.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError(f"Job with id {job_id} not found.")
        for k, v in kwargs.items():
            if hasattr(job, k):
                setattr(job, k, v)
        self.session.add(job)
        self.session.flush()
        return job

    def delete(self, job_id: int) -> bool:
        job = self.get_by_id(job_id)
        if not job:
            return False
        self.session.delete(job)
        self.session.flush()
        return True


class SqlCardRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, card_id: int) -> Card | None:
        return self.session.exec(select(Card).where(Card.id == card_id)).first()

    def get_by_remote_id(self, project_id: int, remote_id: str) -> Card | None:
        stmt = select(Card).where(Card.project_id == project_id, Card.remote_id == remote_id)
        return self.session.exec(stmt).first()

    def list_by_project(self, project_id: int, include_removed: bool = False) -> list[Card]:
        stmt = select(Card).where(Card.project_id == project_id)
        if not include_removed:
            stmt = stmt.where(Card.removed == False)  # noqa: E712
        stmt = stmt.order_by(Card.title)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        project_id: int,
        remote_id: str,
        title: str,
        body: str,
        column_name: str,
        url: str | None = None,
        issue_number: int | None = None,
        content_hash: str | None = None,
    ) -> Card:
        card = Card(
            project_id=project_id,
            remote_id=remote_id,
            title=title,
            body=body,
            column_name=column_name,
            url=url,
            issue_number=issue_number,
            content_hash=content_hash,
            rework_count=0,
            first_seen_at=utc_now(),
            last_seen_at=utc_now(),
            removed=False,
        )
        self.session.add(card)
        self.session.flush()
        return card

    def update(self, card_id: int, **kwargs: Any) -> Card:
        card = self.get_by_id(card_id)
        if not card:
            raise EntityNotFoundError(f"Card with id {card_id} not found.")
        for k, v in kwargs.items():
            if hasattr(card, k):
                setattr(card, k, v)
        self.session.add(card)
        self.session.flush()
        return card


class SqlCardEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_card(self, card_id: int) -> list[CardEvent]:
        stmt = select(CardEvent).where(CardEvent.card_id == card_id).order_by(desc(CardEvent.created_at))
        return list(self.session.exec(stmt).all())

    def list_recent(self, limit: int = 50) -> list[CardEvent]:
        stmt = select(CardEvent).order_by(desc(CardEvent.created_at)).limit(limit)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        card_id: int,
        event_type: str,
        from_column: str | None = None,
        to_column: str | None = None,
        is_rework: bool = False,
    ) -> CardEvent:
        event = CardEvent(
            card_id=card_id,
            event_type=event_type,
            from_column=from_column,
            to_column=to_column,
            is_rework=is_rework,
            created_at=utc_now(),
        )
        self.session.add(event)
        self.session.flush()
        return event


class SqlCliModelRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_provider(self, cli_provider: str, available_only: bool = True) -> list[CliModel]:
        stmt = select(CliModel).where(CliModel.cli_provider == cli_provider)
        if available_only:
            stmt = stmt.where(CliModel.available == True)  # noqa: E712
        stmt = stmt.order_by(CliModel.label)
        return list(self.session.exec(stmt).all())

    def list_all(self, available_only: bool = False) -> list[CliModel]:
        stmt = select(CliModel)
        if available_only:
            stmt = stmt.where(CliModel.available == True)  # noqa: E712
        stmt = stmt.order_by(CliModel.cli_provider, CliModel.label)
        return list(self.session.exec(stmt).all())

    def upsert_models(self, cli_provider: str, models: list[Any]) -> None:
        # Mark existing models for this provider as available=False
        existing = self.session.exec(select(CliModel).where(CliModel.cli_provider == cli_provider)).all()
        existing_map = {m.model_id: m for m in existing}

        seen_ids = set()
        for m in models:
            m_id = getattr(m, "id", None) or getattr(m, "model_id", None)
            m_label = getattr(m, "label", m_id)
            m_family = getattr(m, "family", "general")
            if not m_id:
                continue
            seen_ids.add(m_id)
            if m_id in existing_map:
                db_model = existing_map[m_id]
                db_model.label = m_label
                db_model.family = m_family
                db_model.available = True
                db_model.last_synced_at = utc_now()
                self.session.add(db_model)
            else:
                db_model = CliModel(
                    cli_provider=cli_provider,
                    model_id=m_id,
                    label=m_label,
                    family=m_family,
                    available=True,
                    last_synced_at=utc_now(),
                )
                self.session.add(db_model)

        for m_id, db_model in existing_map.items():
            if m_id not in seen_ids:
                db_model.available = False
                self.session.add(db_model)

        self.session.flush()


class SqlPipelineRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, run_id: int) -> PipelineRun | None:
        return self.session.exec(select(PipelineRun).where(PipelineRun.id == run_id)).first()

    def list_recent(self, limit: int = 50) -> list[PipelineRun]:
        stmt = select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(limit)
        return list(self.session.exec(stmt).all())

    def create(
        self,
        trigger: str,
        project_provider_used: str,
        project_id: int | None = None,
        cli_provider_used: str | None = None,
    ) -> PipelineRun:
        run = PipelineRun(
            trigger=trigger,
            project_provider_used=project_provider_used,
            project_id=project_id,
            cli_provider_used=cli_provider_used,
            cards_synced=0,
            jobs_created=0,
            status="ok",
            started_at=utc_now(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update(self, run_id: int, **kwargs: Any) -> PipelineRun:
        run = self.get_by_id(run_id)
        if not run:
            raise EntityNotFoundError(f"PipelineRun with id {run_id} not found.")
        for k, v in kwargs.items():
            if hasattr(run, k):
                setattr(run, k, v)
        self.session.add(run)
        self.session.flush()
        return run
