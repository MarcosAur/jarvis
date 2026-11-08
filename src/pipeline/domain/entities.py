from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CardEventType(str, Enum):
    CREATED = "created"
    COLUMN_CHANGED = "column_changed"
    CONTENT_CHANGED = "content_changed"
    REMOVED = "removed"


class RunTrigger(str, Enum):
    WEB_PROJECT = "web_project"
    WEB_ALL = "web_all"
    CLI = "cli"


class RunStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass(frozen=True)
class ModelOption:
    id: str  # ex.: "gemini-4-argon-medium"
    label: str  # ex.: "Gemini 4 Argon (Medium)"
    family: str  # ex.: "gemini", "claude", "openai"
    cli_provider: str = ""


@dataclass(frozen=True)
class CliPromptRequest:
    model_id: str
    system_prompt_markdown: str  # vem do prompt_markdown do Agente
    task_prompt: str  # montado com título/descrição do card e contexto
    working_dir: Path  # local_path do Projeto


@dataclass(frozen=True)
class CliPromptResult:
    success: bool
    output_text: str
    tokens_in: int = 0
    tokens_out: int = 0
    raw_meta: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


@dataclass(frozen=True)
class SettingFieldSpec:
    name: str
    label: str
    type: str = "text"  # "text", "password", "number", "select"
    required: bool = False
    default: Any = None
    description: str = ""
    is_secret: bool = False
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, label) para select


@dataclass(frozen=True)
class RemoteCard:
    remote_id: str  # ID no provedor externo
    title: str
    body: str
    column_name: str  # Nome exato da coluna onde o card está no quadro
    url: str | None = None
    issue_number: int | None = None
    repository: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    updated_at: datetime | None = None


@dataclass(frozen=True)
class BoardInfo:
    project_key: str
    title: str
    total_cards: int
    columns: list[str]
    raw_meta: dict[str, Any] = field(default_factory=dict)
