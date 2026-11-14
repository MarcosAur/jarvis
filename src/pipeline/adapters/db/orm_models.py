from datetime import datetime, timezone
from typing import Any
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppSettings(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int | None = Field(default=1, primary_key=True)
    default_cli_provider: str = Field(default="agy")
    active_project_provider: str = Field(default="github")
    provider_settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utc_now)


class CliModel(SQLModel, table=True):
    __tablename__ = "cli_models"

    id: int | None = Field(default=None, primary_key=True)
    cli_provider: str = Field(index=True)
    model_id: str = Field(index=True)
    label: str
    family: str = Field(default="general")
    available: bool = Field(default=True)
    last_synced_at: datetime = Field(default_factory=utc_now)


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    cli_provider: str = Field(index=True)
    model_id: str
    prompt_markdown: str = Field(default="")
    max_parallel_executions: int = Field(default=1)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    project_key: str = Field(unique=True, index=True)
    project_provider: str = Field(default="github", index=True)
    name: str
    local_path: str
    active: bool = Field(default=True)
    last_run_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FlowColumn(SQLModel, table=True):
    __tablename__ = "flow_columns"

    id: int | None = Field(default=None, primary_key=True)
    identifier: str = Field(unique=True, index=True)
    column_name: str = Field(unique=True, index=True)
    agent_id: int | None = Field(default=None, foreign_key="agents.id")
    next_column_name: str | None = Field(default=None)
    order_index: int = Field(default=0)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    remote_id: str = Field(index=True)
    title: str
    body: str = Field(default="")
    column_name: str = Field(index=True)
    url: str | None = Field(default=None)
    issue_number: int | None = Field(default=None)
    content_hash: str | None = Field(default=None)
    rework_count: int = Field(default=0)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    removed: bool = Field(default=False)


class CardEvent(SQLModel, table=True):
    __tablename__ = "card_events"

    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    event_type: str = Field(index=True)
    from_column: str | None = Field(default=None)
    to_column: str | None = Field(default=None)
    is_rework: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    flow_column_id: int = Field(foreign_key="flow_columns.id", index=True)
    agent_id: int | None = Field(default=None, foreign_key="agents.id")
    cli_provider_snapshot: str | None = Field(default=None)
    model_id_snapshot: str | None = Field(default=None)
    target_column_snapshot: str | None = Field(default=None)
    iteration: int = Field(default=1)
    state: str = Field(default="pending", index=True)
    celery_task_id: str | None = Field(default=None, index=True)
    process_status: str | None = Field(default=None)
    output_summary: str | None = Field(default=None)
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)


class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id")
    trigger: str = Field(default="web_project")
    project_provider_used: str
    cli_provider_used: str | None = Field(default=None)
    cards_synced: int = Field(default=0)
    jobs_created: int = Field(default=0)
    status: str = Field(default="ok")
    error: str | None = Field(default=None)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = Field(default=None)

