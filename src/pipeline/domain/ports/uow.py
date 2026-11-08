from typing import Any, Protocol, runtime_checkable
from pipeline.domain.ports.repositories import (
    AgentRepository,
    CardEventRepository,
    CardRepository,
    CliModelRepository,
    FlowColumnRepository,
    JobRepository,
    PipelineRunRepository,
    ProjectRepository,
    SettingsRepository,
)


@runtime_checkable
class UnitOfWork(Protocol):
    """Unit of Work interface coordinating transactional repository operations."""

    settings: SettingsRepository
    agents: AgentRepository
    projects: ProjectRepository
    columns: FlowColumnRepository
    jobs: JobRepository
    cards: CardRepository
    events: CardEventRepository
    models: CliModelRepository
    runs: PipelineRunRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
