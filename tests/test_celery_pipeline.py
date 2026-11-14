import sqlite3
import uuid
from unittest.mock import patch
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from pipeline.adapters.db.engine import init_db
from pipeline.adapters.db.seed import seed_database
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.application.sync_service import SyncService
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.celery_app import celery_app
from pipeline.config import Config, compute_celery_timeouts, config
from pipeline.domain.entities import RemoteCard
from pipeline.tasks import execute_job_task, run_pipeline_task
from pipeline.web.app import app
from pipeline.web.dependencies import get_job_dispatcher
from tests.fakes import FakeCliProvider, FakeJobDispatcher, FakeProjectProvider


def test_celery_timeouts_derived_from_agent_timeout():
    soft, hard = compute_celery_timeouts(agent_timeout_seconds=600, overhead_seconds=120, grace_seconds=60)
    assert soft == 720
    assert hard == 780
    assert soft > 600
    assert hard > soft

    # Even if overhead/grace are 0 or negative, Celery timeouts remain strictly greater
    soft_min, hard_min = compute_celery_timeouts(agent_timeout_seconds=300, overhead_seconds=0, grace_seconds=-10)
    assert soft_min > 300
    assert hard_min > soft_min

    # Config properties derive from CLI_TIMEOUT_SECONDS
    custom_cfg = Config(CLI_TIMEOUT_SECONDS=900, CELERY_TIMEOUT_OVERHEAD_SECONDS=150, CELERY_HARD_TIMEOUT_GRACE_SECONDS=45)
    assert custom_cfg.celery_soft_time_limit == 1050
    assert custom_cfg.celery_time_limit == 1095
    assert custom_cfg.celery_soft_time_limit > custom_cfg.CLI_TIMEOUT_SECONDS
    assert custom_cfg.celery_time_limit > custom_cfg.celery_soft_time_limit

    # Celery app & task inherit timeouts greater than agent timeout
    assert celery_app.conf.task_soft_time_limit == config.celery_soft_time_limit
    assert celery_app.conf.task_time_limit == config.celery_time_limit
    assert celery_app.conf.task_soft_time_limit > config.CLI_TIMEOUT_SECONDS
    assert execute_job_task.soft_time_limit > config.CLI_TIMEOUT_SECONDS
    assert execute_job_task.time_limit > execute_job_task.soft_time_limit


def test_celery_beat_schedule_is_configured():
    schedule = celery_app.conf.beat_schedule
    assert "run-pipeline-periodic" in schedule
    entry = schedule["run-pipeline-periodic"]
    assert entry["task"] == "pipeline.tasks.run_pipeline"
    assert entry["schedule"] == float(max(config.CELERY_PIPELINE_INTERVAL_SECONDS, 5))


def test_orchestrator_dispatches_jobs_and_revokes_cancelled():
    mem_engine = create_engine("sqlite:///:memory:")
    init_db(mem_engine)
    from sqlmodel import Session

    uow_fact = lambda: SqlAlchemyUnitOfWork(lambda: Session(mem_engine, expire_on_commit=False))
    seed_database(uow_fact())

    remote_cards = [
        RemoteCard(remote_id="c-1", title="Card Arquitetura", body="Analisar", column_name="To architect"),
    ]
    fake_board = FakeProjectProvider(remote_cards)
    project_registry.register(fake_board)

    with uow_fact() as uow:
        uow.settings.update(
            default_cli_provider="fake_cli",
            active_project_provider="fake_board",
            provider_settings={},
        )
        proj = uow.projects.create(
            project_key="proj-dispatch",
            name="Projeto Dispatch",
            local_path="/tmp",
            active=True,
        )
        uow.commit()
        project_id = proj.id

    fake_dispatcher = FakeJobDispatcher()
    orchestrator = PipelineOrchestrator(uow_fact, SyncService(), job_dispatcher=fake_dispatcher)
    run = orchestrator.run_for_project(project_id, trigger="celery_beat")

    assert run.status == "ok"
    assert run.jobs_created == 1
    assert len(fake_dispatcher.dispatched_jobs) == 1

    dispatched_job_id = fake_dispatcher.dispatched_jobs[0]
    with uow_fact() as uow:
        job = uow.jobs.get_by_id(dispatched_job_id)
        assert job is not None
        assert job.celery_task_id == f"fake-task-{dispatched_job_id}"
        assert job.process_status == "Na fila do Celery"

    # Now simulate card moving out of the column on the external board -> job cancelled & revoked
    fake_board.cards = [
        RemoteCard(remote_id="c-1", title="Card Arquitetura", body="Analisar", column_name="Done"),
    ]
    orchestrator.run_for_project(project_id, trigger="celery_beat")
    assert f"fake-task-{dispatched_job_id}" in fake_dispatcher.revoked_tasks

    with uow_fact() as uow:
        job = uow.jobs.get_by_id(dispatched_job_id)
        assert job.state == "cancelled"
        assert "Cancelado" in (job.process_status or "")


def test_celery_eager_execution_runs_job_and_skips_cancelled():
    uid = uuid.uuid4().hex[:6]
    fake_cli = FakeCliProvider()
    cli_registry.register(fake_cli)

    remote_cards = [
        RemoteCard(remote_id=f"rc-{uid}", title=f"Card Celery {uid}", body="Executar via Celery", column_name="To architect"),
    ]
    fake_board = FakeProjectProvider(remote_cards)
    project_registry.register(fake_board)

    with SqlAlchemyUnitOfWork() as uow:
        orig_settings = uow.settings.get()
        orig_cli = orig_settings.default_cli_provider
        orig_proj_provider = orig_settings.active_project_provider
        orig_provider_settings = dict(orig_settings.provider_settings or {})

        uow.settings.update(
            default_cli_provider="fake_cli",
            active_project_provider="fake_board",
            provider_settings={},
        )
        agent = uow.agents.create(
            name=f"Agente Celery {uid}",
            cli_provider="fake_cli",
            model_id="fake-model-1",
            prompt_markdown="# Prompt",
            active=True,
        )
        proj = uow.projects.create(
            project_key=f"celery-proj-{uid}",
            name=f"Projeto Celery {uid}",
            local_path="/tmp",
            active=True,
        )
        col = uow.columns.get_by_identifier("to_architect")
        orig_col_agent_id = col.agent_id
        uow.columns.update(col.id, agent_id=agent.id)
        uow.commit()
        proj_id = proj.id
        col_id = col.id

    orig_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        res = run_pipeline_task.delay(project_id=proj_id, trigger="celery_beat").get()
        assert res["status"] == "ok"
        assert res["jobs_created"] == 1

        with SqlAlchemyUnitOfWork() as uow:
            jobs = uow.jobs.list_all(project_id=proj_id)
            assert len(jobs) == 1
            job = jobs[0]
            assert job.state == "succeeded"
            assert job.process_status == "Concluído com sucesso"
            assert job.celery_task_id is not None
            assert "fake prompt" in (job.output_summary or "")

            # Create a cancelled job and verify execute_job_task skips it
            card = uow.cards.get_by_remote_id(proj_id, f"rc-{uid}")
            cancelled_job = uow.jobs.create(
                project_id=proj_id,
                card_id=card.id,
                flow_column_id=col_id,
                agent_id=job.agent_id,
                cli_provider_snapshot="fake_cli",
                model_id_snapshot="fake-model-1",
                target_column_snapshot="Architected",
                state="cancelled",
            )
            uow.commit()
            cancelled_id = cancelled_job.id

        skip_res = execute_job_task.delay(cancelled_id).get()
        assert skip_res["skipped"] is True
    finally:
        celery_app.conf.task_always_eager = orig_eager
        with SqlAlchemyUnitOfWork() as uow:
            uow.columns.update(col_id, agent_id=orig_col_agent_id)
            uow.settings.update(
                default_cli_provider=orig_cli,
                active_project_provider=orig_proj_provider,
                provider_settings=orig_provider_settings,
            )
            uow.commit()


def test_celery_soft_timeout_marks_job_failed():
    uid = uuid.uuid4().hex[:6]
    with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.create(
            project_key=f"timeout-proj-{uid}",
            name=f"Projeto Timeout {uid}",
            local_path="/tmp",
            active=True,
        )
        card = uow.cards.create(
            project_id=proj.id,
            remote_id=f"to-{uid}",
            title="Card Timeout",
            body="Teste timeout",
            column_name="To architect",
        )
        col = uow.columns.get_by_identifier("to_architect")
        job = uow.jobs.create(
            project_id=proj.id,
            card_id=card.id,
            flow_column_id=col.id,
            agent_id=col.agent_id,
            cli_provider_snapshot="agy",
            model_id_snapshot="gemini-4-argon-medium",
            target_column_snapshot="Architected",
            state="pending",
        )
        uow.commit()
        job_id = job.id

    with patch("pipeline.tasks.JobRunnerService.run_job", side_effect=SoftTimeLimitExceeded()):
        with pytest.raises(SoftTimeLimitExceeded):
            execute_job_task.apply(args=[job_id], throw=True)

    with SqlAlchemyUnitOfWork() as uow:
        failed_job = uow.jobs.get_by_id(job_id)
        assert failed_job.state == "failed"
        assert failed_job.process_status == "Timeout do Celery excedido"
        assert str(config.celery_soft_time_limit) in (failed_job.error or "")
        assert str(config.CLI_TIMEOUT_SECONDS) in (failed_job.error or "")


def test_web_removes_job_execution_and_shows_celery_feedback():
    uid = uuid.uuid4().hex[:6]
    fake_dispatcher = FakeJobDispatcher(broker_available=True, workers_online=2)
    app.dependency_overrides[get_job_dispatcher] = lambda: fake_dispatcher

    try:
        with SqlAlchemyUnitOfWork() as uow:
            proj = uow.projects.create(
                project_key=f"web-celery-{uid}",
                name=f"Projeto Web Celery {uid}",
                local_path="/tmp",
                active=True,
            )
            card = uow.cards.create(
                project_id=proj.id,
                remote_id=f"wc-{uid}",
                title=f"Card Web {uid}",
                body="Conteúdo",
                column_name="To architect",
            )
            col = uow.columns.get_by_identifier("to_architect")
            uow.commit()
            proj_id = proj.id
            card_id = card.id
            col_id = col.id

        client = TestClient(app)

        # 1. Execution endpoints must not exist on frontend
        resp_run_all = client.post("/jobs/run-all", data={"mode": "live"})
        assert resp_run_all.status_code in (404, 405, 422)

        resp_run_one = client.post("/jobs/1/run", data={"mode": "live"})
        assert resp_run_one.status_code in (404, 405)

        # 2. Creating a job via web enqueues it in Celery instead of executing synchronously
        resp_create = client.post(
            "/jobs/new",
            data={"project_id": str(proj_id), "card_id": str(card_id), "flow_column_id": str(col_id)},
            follow_redirects=True,
        )
        assert resp_create.status_code == 200
        assert len(fake_dispatcher.dispatched_jobs) == 1
        created_job_id = fake_dispatcher.dispatched_jobs[0]

        # 3. Jobs list shows Celery status, process feedback, HTMX polling, and NO execute buttons
        assert "2 worker(s) online" in resp_create.text
        assert "Na fila do Celery" in resp_create.text
        assert "/jobs/partials/content" in resp_create.text
        assert "▶ Executar" not in resp_create.text
        assert "Executar Pendentes" not in resp_create.text

        # 4. Partial endpoint works for HTMX live updates
        resp_partial = client.get("/jobs/partials/content")
        assert resp_partial.status_code == 200
        assert f"#{created_job_id}" in resp_partial.text

        # 5. Job detail page shows Celery task ID, process status, timeouts, and NO execute buttons
        resp_detail = client.get(f"/jobs/{created_job_id}")
        assert resp_detail.status_code == 200
        assert f"fake-task-{created_job_id}" in resp_detail.text
        assert "Na fila do Celery" in resp_detail.text
        assert f"/jobs/{created_job_id}/partials/status" in resp_detail.text
        assert "Executar com IA" not in resp_detail.text
        assert "Dry-Run" not in resp_detail.text

        resp_detail_partial = client.get(f"/jobs/{created_job_id}/partials/status")
        assert resp_detail_partial.status_code == 200
        assert "Metadados & Status do Processo" in resp_detail_partial.text

        # 6. Cancelling revokes the Celery task
        resp_cancel = client.post(f"/jobs/{created_job_id}/cancel", follow_redirects=True)
        assert resp_cancel.status_code == 200
        assert f"fake-task-{created_job_id}" in fake_dispatcher.revoked_tasks

        # 7. Retrying re-dispatches to Celery
        resp_retry = client.post(f"/jobs/{created_job_id}/retry", follow_redirects=True)
        assert resp_retry.status_code == 200
        assert fake_dispatcher.dispatched_jobs.count(created_job_id) == 2
    finally:
        app.dependency_overrides.clear()


def test_sqlite_init_db_migrates_legacy_jobs_table(tmp_path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            flow_column_id INTEGER NOT NULL,
            agent_id INTEGER,
            cli_provider_snapshot VARCHAR,
            model_id_snapshot VARCHAR,
            target_column_snapshot VARCHAR,
            iteration INTEGER NOT NULL,
            state VARCHAR NOT NULL,
            output_summary VARCHAR,
            error VARCHAR,
            created_at DATETIME NOT NULL,
            started_at DATETIME,
            finished_at DATETIME
        )
        """
    )
    conn.commit()
    conn.close()

    legacy_engine = create_engine(f"sqlite:///{db_file}")
    init_db(legacy_engine)

    conn = sqlite3.connect(db_file)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    conn.close()
    assert "celery_task_id" in cols
    assert "process_status" in cols
