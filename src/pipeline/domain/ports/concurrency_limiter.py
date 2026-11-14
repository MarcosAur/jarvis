from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConcurrencyAcquireResult:
    acquired: bool
    active_count: int
    max_parallel: int


@runtime_checkable
class AgentConcurrencyLimiter(Protocol):
    """Port for enforcing per-agent, per-project execution concurrency across workers."""

    def try_acquire(
        self,
        agent_id: int,
        project_id: int,
        job_id: int,
        max_parallel: int,
        ttl_seconds: int,
    ) -> ConcurrencyAcquireResult:
        """Attempt to acquire an execution slot for (agent_id, project_id)."""
        ...

    def release(self, agent_id: int, project_id: int, job_id: int) -> None:
        """Release the slot held by job_id for (agent_id, project_id)."""
        ...

    def active_slots(self, agent_id: int, project_id: int) -> int:
        """Return currently active (unexpired) execution count for (agent_id, project_id)."""
        ...
