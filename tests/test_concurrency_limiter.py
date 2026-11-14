import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
import pytest
from celery.exceptions import Retry
from sqlalchemy import create_engine
from pipeline.adapters.celery_dispatcher import CeleryJobDispatcher
from pipeline.adapters.db.engine import init_db
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.adapters.redis_concurrency_limiter import InMemoryAgentConcurrencyLimiter
from pipeline.domain.ports.concurrency_limiter import AgentConcurrencyLimiter
from pipeline.tasks import execute_job_task


def test_in_memory_limiter_scopes_by_agent_and_project():
    limiter = InMemoryAgentConcurrencyLimiter()
    assert isinstance(limiter, AgentConcurrencyLimiter)

    # Dev agent (limit=1) in Project 10: first succeeds, second is blocked
    res1 = limiter.try_acquire(agent_id=1, project_id=10, job_id=101, max_parallel=1, ttl_seconds=60)
    assert res1.acquired is True
    assert res1.active_count == 1

    res2 = limiter.try_acquire(agent_id=1, project_id=10, job_id=102, max_parallel=1, ttl_seconds=60)
    assert res2.acquired is False
    assert res2.active_count == 1

    # Same Dev agent in Project 20 IS allowed simultaneously (independent per-project slot)
    res_proj20 = limiter.try_acquire(agent_id=1, project_id=20, job_id=201, max_parallel=1, ttl_seconds=60)
    assert res_proj20.acquired is True
    assert res_proj20.active_count == 1

    # Release in Project 10 frees job 102
    limiter.release(agent_id=1, project_id=10, job_id=101)
    res2_retry = limiter.try_acquire(agent_id=1, project_id=10, job_id=102, max_parallel=1, ttl_seconds=60)
    assert res2_retry.acquired is True
    assert limiter.active_slots(agent_id=1, project_id=10) == 1


def test_in_memory_limiter_parallel_architect_threads():
    limiter = InMemoryAgentConcurrencyLimiter()

    def try_job(jid: int) -> bool:
        return limiter.try_acquire(agent_id=2, project_id=10, job_id=jid, max_parallel=3, ttl_seconds=60).acquired

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(try_job, [1, 2, 3, 4, 5, 6]))

    assert sum(1 for ok in outcomes if ok) == 3
    assert limiter.active_slots(agent_id=2, project_id=10) == 3


def test_execute_job_task_retries_when_agent_project_slot_is_full():
    uid = uuid.uuid4().hex[:6]
    with SqlAlchemyUnitOfWork() as uow:
        agent = uow.agents.create(
            name=f"Dev Sequencial {uid}",
            cli_provider="fake_cli",
            model_id="fake-model-1",
            prompt_markdown="Dev",
            max_parallel_executions=1,
        )
        proj = uow.projects.create(
            project_key=f"conc-proj-{uid}",
            name=f"Proj Conc {uid}",
            local_path="/tmp",
            active=True,
        )
        card = uow.cards.create(
            project_id=proj.id,
            remote_id=f"c-{uid}",
            title="Card Dev",
            body="body",
            column_name="In Progress",
        )
        col = uow.columns.get_by_identifier("to_architect")
        job1 = uow.jobs.create(
            project_id=proj.id,
            card_id=card.id,
            flow_column_id=col.id,
            agent_id=agent.id,
            cli_provider_snapshot="fake_cli",
            model_id_snapshot="fake-model-1",
            target_column_snapshot="Architected",
            state="pending",
        )
        job2 = uow.jobs.create(
            project_id=proj.id,
            card_id=card.id,
            flow_column_id=col.id,
            agent_id=agent.id,
            cli_provider_snapshot="fake_cli",
            model_id_snapshot="fake-model-1",
            target_column_snapshot="Architected",
            state="pending",
        )
        uow.commit()
        agent_id, proj_id, job1_id, job2_id = agent.id, proj.id, job1.id, job2.id

    limiter = InMemoryAgentConcurrencyLimiter()
    # Pre-occupy slot for (agent_id, proj_id) with job1
    assert limiter.try_acquire(agent_id, proj_id, job1_id, max_parallel=1, ttl_seconds=60).acquired is True

    with patch("pipeline.tasks.get_concurrency_limiter", return_value=limiter):
        with pytest.raises(Retry):
            execute_job_task.apply(args=[job2_id], throw=True)

    # Job 2 must remain pending (NOT failed) with descriptive waiting process_status
    with SqlAlchemyUnitOfWork() as uow:
        j2 = uow.jobs.get_by_id(job2_id)
        assert j2.state == "pending"
        assert "1/1 em execução" in (j2.process_status or "")


def test_celery_dispatcher_inspects_pool_concurrency_across_nodes():
    mock_conn = MagicMock()
    mock_inspector = MagicMock()
    mock_inspector.ping.return_value = {"celery@node1": {"ok": "pong"}}
    mock_inspector.stats.return_value = {"celery@node1": {"pool": {"max-concurrency": 4}}}
    mock_inspector.active.return_value = {"celery@node1": [{"id": "task-1"}, {"id": "task-2"}]}

    with patch("pipeline.adapters.celery_dispatcher.celery_app") as mock_app:
        mock_app.connection_for_read.return_value.__enter__.return_value = mock_conn
        mock_app.control.inspect.return_value = mock_inspector

        health = CeleryJobDispatcher().get_worker_health()

    assert health.broker_available is True
    assert health.workers_online == 4
    assert health.nodes_online == 1
    assert health.active_tasks_count == 2
    assert health.worker_names == ["celery@node1"]


def test_sqlite_init_db_migrates_legacy_agents_table(tmp_path):
    db_file = tmp_path / "legacy_agents.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL,
            cli_provider VARCHAR NOT NULL,
            model_id VARCHAR NOT NULL,
            prompt_markdown VARCHAR NOT NULL DEFAULT '',
            active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    eng = create_engine(f"sqlite:///{db_file}")
    init_db(eng)
    eng.dispose()

    conn = sqlite3.connect(db_file)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
    conn.close()

    assert "max_parallel_executions" in cols
