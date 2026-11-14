from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CeleryTaskStatus:
    task_id: str
    state: str
    detail: str | None = None


@dataclass(frozen=True)
class WorkerHealthStatus:
    broker_available: bool
    workers_online: int
    worker_names: list[str]
    error: str | None = None


@runtime_checkable
class JobDispatcher(Protocol):
    """Port for dispatching and inspecting asynchronous background jobs (e.g. Celery)."""

    def dispatch_job(self, job_id: int) -> str | None:
        """Enqueues a job for asynchronous execution and returns its task ID."""
        ...

    def dispatch_pipeline(self, project_id: int | None = None) -> str | None:
        """Enqueues a pipeline run and returns its task ID."""
        ...

    def revoke_job(self, task_id: str) -> bool:
        """Attempts to revoke a pending background task."""
        ...

    def get_task_status(self, task_id: str) -> CeleryTaskStatus:
        """Returns the current task status from the background backend."""
        ...

    def get_worker_health(self) -> WorkerHealthStatus:
        """Checks broker and worker availability."""
        ...
