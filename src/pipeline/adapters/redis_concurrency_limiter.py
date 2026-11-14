import threading
import time
from typing import Any
import redis
from pipeline.config import config
from pipeline.domain.ports.concurrency_limiter import (
    AgentConcurrencyLimiter,
    ConcurrencyAcquireResult,
)

_ACQUIRE_LUA = """
local key = KEYS[1]
local job_id = ARGV[1]
local now = tonumber(ARGV[2])
local expires_at = tonumber(ARGV[3])
local max_parallel = tonumber(ARGV[4])
local key_ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now)

local existing = redis.call('ZSCORE', key, job_id)
if existing then
    redis.call('ZADD', key, expires_at, job_id)
    redis.call('EXPIRE', key, key_ttl)
    local count = redis.call('ZCARD', key)
    return {1, count}
end

local count = redis.call('ZCARD', key)
if count < max_parallel then
    redis.call('ZADD', key, expires_at, job_id)
    redis.call('EXPIRE', key, key_ttl)
    return {1, count + 1}
end

return {0, count}
"""

_ACTIVE_COUNT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
return redis.call('ZCARD', key)
"""


class RedisAgentConcurrencyLimiter(AgentConcurrencyLimiter):
    """Distributed per-(agent, project) semaphore backed by Redis ZSET + Lua."""

    def __init__(self, redis_url: str | None = None, client: Any | None = None) -> None:
        self._client = client or redis.Redis.from_url(
            redis_url or config.CELERY_BROKER_URL,
            decode_responses=True,
        )
        self._acquire_script = self._client.register_script(_ACQUIRE_LUA)
        self._active_script = self._client.register_script(_ACTIVE_COUNT_LUA)

    @staticmethod
    def _slot_key(agent_id: int, project_id: int) -> str:
        return f"pipeline:agent_slots:{agent_id}:{project_id}"

    def try_acquire(
        self,
        agent_id: int,
        project_id: int,
        job_id: int,
        max_parallel: int,
        ttl_seconds: int,
    ) -> ConcurrencyAcquireResult:
        safe_limit = max(int(max_parallel), 1)
        safe_ttl = max(int(ttl_seconds), 30)
        now = time.time()
        expires_at = now + safe_ttl
        key_ttl = safe_ttl + 60

        result = self._acquire_script(
            keys=[self._slot_key(agent_id, project_id)],
            args=[str(job_id), now, expires_at, safe_limit, key_ttl],
        )
        acquired = bool(int(result[0]))
        active_count = int(result[1])
        return ConcurrencyAcquireResult(
            acquired=acquired,
            active_count=active_count,
            max_parallel=safe_limit,
        )

    def release(self, agent_id: int, project_id: int, job_id: int) -> None:
        self._client.zrem(self._slot_key(agent_id, project_id), str(job_id))

    def active_slots(self, agent_id: int, project_id: int) -> int:
        count = self._active_script(
            keys=[self._slot_key(agent_id, project_id)],
            args=[time.time()],
        )
        return int(count or 0)


class InMemoryAgentConcurrencyLimiter(AgentConcurrencyLimiter):
    """Thread-safe in-memory fallback limiter for eager mode and unit tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[tuple[int, int], dict[int, float]] = {}

    def _prune_locked(self, key: tuple[int, int], now: float) -> dict[int, float]:
        entries = self._slots.setdefault(key, {})
        expired = [jid for jid, exp in entries.items() if exp <= now]
        for jid in expired:
            del entries[jid]
        return entries

    def try_acquire(
        self,
        agent_id: int,
        project_id: int,
        job_id: int,
        max_parallel: int,
        ttl_seconds: int,
    ) -> ConcurrencyAcquireResult:
        safe_limit = max(int(max_parallel), 1)
        safe_ttl = max(int(ttl_seconds), 30)
        now = time.monotonic()
        expires_at = now + safe_ttl
        key = (agent_id, project_id)

        with self._lock:
            entries = self._prune_locked(key, now)
            if job_id in entries:
                entries[job_id] = expires_at
                return ConcurrencyAcquireResult(acquired=True, active_count=len(entries), max_parallel=safe_limit)
            if len(entries) < safe_limit:
                entries[job_id] = expires_at
                return ConcurrencyAcquireResult(acquired=True, active_count=len(entries), max_parallel=safe_limit)
            return ConcurrencyAcquireResult(acquired=False, active_count=len(entries), max_parallel=safe_limit)

    def release(self, agent_id: int, project_id: int, job_id: int) -> None:
        key = (agent_id, project_id)
        with self._lock:
            entries = self._slots.get(key)
            if entries is not None:
                entries.pop(job_id, None)

    def active_slots(self, agent_id: int, project_id: int) -> int:
        now = time.monotonic()
        with self._lock:
            return len(self._prune_locked((agent_id, project_id), now))


_in_memory_limiter = InMemoryAgentConcurrencyLimiter()
_redis_limiter: RedisAgentConcurrencyLimiter | None = None


def get_concurrency_limiter(
    broker_url: str | None = None,
    *,
    always_eager: bool = False,
) -> AgentConcurrencyLimiter:
    """Return Redis limiter for multi-worker Redis brokers, or InMemory fallback."""
    global _redis_limiter
    url = (broker_url or config.CELERY_BROKER_URL or "").strip()
    if not (config.CELERY_TASK_ALWAYS_EAGER or always_eager) and url.startswith(("redis://", "rediss://")):
        if _redis_limiter is None:
            _redis_limiter = RedisAgentConcurrencyLimiter(redis_url=url)
        return _redis_limiter
    return _in_memory_limiter
