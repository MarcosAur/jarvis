from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pipeline.domain.entities import (
    BoardInfo,
    CliPromptRequest,
    CliPromptResult,
    ModelOption,
    RemoteCard,
    SettingFieldSpec,
)
from pipeline.domain.ports.cli_provider import CliModelProvider
from pipeline.domain.ports.job_dispatcher import (
    CeleryTaskStatus,
    JobDispatcher,
    WorkerHealthStatus,
)
from pipeline.domain.ports.project_provider import ProjectProvider


class FakeCliProvider(CliModelProvider):
    provider_key = "fake_cli"
    display_name = "Fake CLI Provider"
    binary_name = "fake_cli"

    def __init__(self, installed: bool = True):
        self._installed = installed
        self.executed_requests: list[CliPromptRequest] = []

    def is_installed(self) -> bool:
        return self._installed

    def list_models(self) -> list[ModelOption]:
        return [
            ModelOption(id="fake-model-1", label="Fake Model 1", family="fake", cli_provider="fake_cli"),
            ModelOption(id="fake-model-2", label="Fake Model 2", family="fake", cli_provider="fake_cli"),
        ]

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        self.executed_requests.append(req)
        return CliPromptResult(
            success=True,
            output_text=f"Resultado do fake prompt para modelo {req.model_id}",
            tokens_in=50,
            tokens_out=100,
        )


class FakeProjectProvider(ProjectProvider):
    provider_key = "fake_board"
    display_name = "Fake Board Provider"

    def __init__(self, cards: list[RemoteCard] | None = None):
        self.cards: list[RemoteCard] = cards or []
        self.moved_cards: list[tuple[str, str, str]] = []  # (project_key, card_id, target_col)
        self.comments: list[tuple[str, str, str]] = []

    def settings_fields(self) -> list[SettingFieldSpec]:
        return [SettingFieldSpec(name="fake_token", label="Fake Token")]

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        return BoardInfo(
            project_key=project_key,
            title="Fake Project",
            total_cards=len(self.cards),
            columns=["Todo", "To architect", "Architected", "In Progress", "Homolog", "Done"],
        )

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        return list(self.cards)

    def move_card(
        self,
        project_key: str,
        remote_card_id: str,
        target_column_name: str,
        settings: dict[str, Any],
    ) -> None:
        self.moved_cards.append((project_key, remote_card_id, target_column_name))
        # Update in-memory card
        new_cards = []
        for c in self.cards:
            if c.remote_id == remote_card_id:
                new_cards.append(RemoteCard(
                    remote_id=c.remote_id,
                    title=c.title,
                    body=c.body,
                    column_name=target_column_name,
                    url=c.url,
                    issue_number=c.issue_number,
                ))
            else:
                new_cards.append(c)
        self.cards = new_cards

    def add_comment(
        self,
        project_key: str,
        remote_card_id: str,
        markdown: str,
        settings: dict[str, Any],
    ) -> None:
        self.comments.append((project_key, remote_card_id, markdown))


class FakeJobDispatcher(JobDispatcher):
    def __init__(self, broker_available: bool = True, workers_online: int = 1):
        self.dispatched_jobs: list[int] = []
        self.dispatched_pipelines: list[int | None] = []
        self.revoked_tasks: list[str] = []
        self.broker_available = broker_available
        self.workers_online = workers_online
        self.task_states: dict[str, str] = {}

    def dispatch_job(self, job_id: int) -> str | None:
        self.dispatched_jobs.append(job_id)
        task_id = f"fake-task-{job_id}"
        self.task_states[task_id] = "PENDING"
        return task_id

    def dispatch_pipeline(self, project_id: int | None = None) -> str | None:
        self.dispatched_pipelines.append(project_id)
        return f"fake-pipeline-{project_id or 'all'}"

    def revoke_job(self, task_id: str) -> bool:
        self.revoked_tasks.append(task_id)
        self.task_states[task_id] = "REVOKED"
        return True

    def get_task_status(self, task_id: str) -> CeleryTaskStatus:
        return CeleryTaskStatus(
            task_id=task_id,
            state=self.task_states.get(task_id, "PENDING"),
        )

    def get_worker_health(self) -> WorkerHealthStatus:
        names = [f"celery@worker-{i+1}" for i in range(self.workers_online)] if self.broker_available else []
        return WorkerHealthStatus(
            broker_available=self.broker_available,
            workers_online=self.workers_online if self.broker_available else 0,
            worker_names=names,
        )
