import sqlite3
import uuid
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from pipeline.adapters.db.engine import init_db
from pipeline.adapters.db.seed import seed_database
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.job_runner_service import JobRunnerService
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.application.sync_service import SyncService
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.domain.entities import RemoteCard
from pipeline.domain.provider_state import (
    get_disabled_cli_providers,
    is_cli_provider_enabled,
    is_project_provider_enabled,
    set_cli_provider_enabled,
    set_project_provider_enabled,
)
from pipeline.web.app import app
from tests.fakes import FakeCliProvider, FakeProjectProvider


def _make_memory_uow_factory():
    mem_engine = create_engine("sqlite:///:memory:")
    init_db(mem_engine)
    uow_factory = lambda: SqlAlchemyUnitOfWork(lambda: Session(mem_engine, expire_on_commit=False))
    seed_database(uow_factory())
    return uow_factory


def test_simultaneous_multi_project_and_multi_cli_providers():
    """Dois projetos ativos com provedores distintos e agentes com CLIs distintas rodam juntos sem trocar configuração global."""
    uow_fact = _make_memory_uow_factory()

    board_a = FakeProjectProvider(
        cards=[RemoteCard(remote_id="gh-1", title="Feature A", body="Repo A", column_name="To architect")]
    )
    board_a.provider_key = "fake_board_a"
    board_a.display_name = "Fake Board A"

    board_b = FakeProjectProvider(
        cards=[RemoteCard(remote_id="jr-1", title="Feature B", body="Repo B", column_name="In Progress")]
    )
    board_b.provider_key = "fake_board_b"
    board_b.display_name = "Fake Board B"

    cli_a = FakeCliProvider(installed=True)
    cli_a.provider_key = "fake_cli_a"
    cli_a.display_name = "Fake CLI A"

    cli_b = FakeCliProvider(installed=True)
    cli_b.provider_key = "fake_cli_b"
    cli_b.display_name = "Fake CLI B"

    project_registry.register(board_a)
    project_registry.register(board_b)
    cli_registry.register(cli_a)
    cli_registry.register(cli_b)

    try:
        with uow_fact() as uow:
            agent_a = uow.agents.create(
                name="Agente Multi A",
                cli_provider="fake_cli_a",
                model_id="fake-model-1",
                prompt_markdown="# Prompt A",
                active=True,
            )
            agent_b = uow.agents.create(
                name="Agente Multi B",
                cli_provider="fake_cli_b",
                model_id="fake-model-2",
                prompt_markdown="# Prompt B",
                active=True,
            )

            col_arch = uow.columns.get_by_identifier("to_architect")
            col_dev = uow.columns.get_by_identifier("in_progress")
            uow.columns.update(col_arch.id, agent_id=agent_a.id)
            uow.columns.update(col_dev.id, agent_id=agent_b.id)

            proj_a = uow.projects.create(
                project_key="org/repo-a",
                project_provider="fake_board_a",
                name="Projeto A (Board A)",
                local_path="/tmp",
                active=True,
            )
            proj_b = uow.projects.create(
                project_key="PROJ-B",
                project_provider="fake_board_b",
                name="Projeto B (Board B)",
                local_path="/tmp",
                active=True,
            )
            uow.commit()
            proj_a_id, proj_b_id = proj_a.id, proj_b.id

        orchestrator = PipelineOrchestrator(uow_fact, SyncService())
        runs = orchestrator.run_all_active(trigger="test_multi")
        assert len(runs) == 2

        runs_by_project = {r.project_id: r for r in runs}
        assert runs_by_project[proj_a_id].project_provider_used == "fake_board_a"
        assert runs_by_project[proj_b_id].project_provider_used == "fake_board_b"
        assert runs_by_project[proj_a_id].status == "ok"
        assert runs_by_project[proj_b_id].status == "ok"
        assert runs_by_project[proj_a_id].jobs_created == 1
        assert runs_by_project[proj_b_id].jobs_created == 1

        with uow_fact() as uow:
            jobs_a = uow.jobs.list_all(project_id=proj_a_id)
            jobs_b = uow.jobs.list_all(project_id=proj_b_id)
            assert len(jobs_a) == 1
            assert len(jobs_b) == 1
            job_a_id = jobs_a[0].id
            job_b_id = jobs_b[0].id

        runner = JobRunnerService(uow_fact)
        res_a = runner.run_job(job_a_id, dry_run=False)
        res_b = runner.run_job(job_b_id, dry_run=False)

        assert res_a["success"] is True
        assert res_b["success"] is True
        assert len(cli_a.executed_requests) == 1
        assert len(cli_b.executed_requests) == 1
        assert len(board_a.moved_cards) == 1
        assert len(board_b.moved_cards) == 1
        assert board_a.moved_cards[0][0] == "org/repo-a"
        assert board_b.moved_cards[0][0] == "PROJ-B"
    finally:
        project_registry._items.pop("fake_board_a", None)
        project_registry._items.pop("fake_board_b", None)
        cli_registry._items.pop("fake_cli_a", None)
        cli_registry._items.pop("fake_cli_b", None)


def test_disabled_project_provider_blocks_orchestrator_and_cli_provider_blocks_runner_and_sync():
    """Provedor de projeto desativado bloqueia sincronização; CLI desativada bloqueia execução de job e sincronização de modelos."""
    uow_fact = _make_memory_uow_factory()

    board = FakeProjectProvider(
        cards=[RemoteCard(remote_id="c-1", title="Card Block", body="Body", column_name="To architect")]
    )
    board.provider_key = "fake_board_toggle"
    board.display_name = "Fake Board Toggle"

    cli = FakeCliProvider(installed=True)
    cli.provider_key = "fake_cli_toggle"
    cli.display_name = "Fake CLI Toggle"

    project_registry.register(board)
    cli_registry.register(cli)

    try:
        with uow_fact() as uow:
            agent = uow.agents.create(
                name="Agente Toggle",
                cli_provider="fake_cli_toggle",
                model_id="fake-model-1",
                prompt_markdown="# Prompt",
                active=True,
            )
            col = uow.columns.get_by_identifier("to_architect")
            uow.columns.update(col.id, agent_id=agent.id)
            proj = uow.projects.create(
                project_key="toggle/repo",
                project_provider="fake_board_toggle",
                name="Projeto Toggle",
                local_path="/tmp",
                active=True,
            )
            # Disable project provider first
            settings = uow.settings.get()
            ps = set_project_provider_enabled(settings.provider_settings, "fake_board_toggle", False)
            uow.settings.update(provider_settings=ps)
            uow.commit()
            proj_id = proj.id
            col_id = col.id
            agent_id = agent.id

        orchestrator = PipelineOrchestrator(uow_fact, SyncService())
        run_disabled = orchestrator.run_for_project(proj_id, trigger="test_disabled")
        assert run_disabled.status == "error"
        assert "desativado nas Configurações" in (run_disabled.error or "")

        # Re-enable project provider, create job via orchestrator, then disable CLI provider
        with uow_fact() as uow:
            settings = uow.settings.get()
            ps = set_project_provider_enabled(settings.provider_settings, "fake_board_toggle", True)
            ps = set_cli_provider_enabled(ps, "fake_cli_toggle", False)
            uow.settings.update(provider_settings=ps)
            uow.commit()

            # Check ModelCatalogService skips disabled CLI provider
            catalog = ModelCatalogService(uow_fact)
            disabled_clis = get_disabled_cli_providers(ps)
            sync_counts = catalog.sync_all_installed_providers(disabled_providers=disabled_clis)
            assert sync_counts["fake_cli_toggle"] == 0
            assert uow.models.list_by_provider("fake_cli_toggle") == []

        run_ok = orchestrator.run_for_project(proj_id, trigger="test_enabled")
        assert run_ok.status == "ok"
        assert run_ok.jobs_created == 1

        with uow_fact() as uow:
            jobs = uow.jobs.list_all(project_id=proj_id)
            assert len(jobs) == 1
            job_id = jobs[0].id

        runner = JobRunnerService(uow_fact)
        res = runner.run_job(job_id, dry_run=False)
        assert res["success"] is False
        assert "desativado nas Configurações" in res["error"]

        with uow_fact() as uow:
            failed_job = uow.jobs.get_by_id(job_id)
            assert failed_job.state == "failed"
            assert failed_job.process_status == "Falha: CLI 'fake_cli_toggle' desativada"
    finally:
        project_registry._items.pop("fake_board_toggle", None)
        cli_registry._items.pop("fake_cli_toggle", None)


def test_web_provider_toggles_hide_disabled_options_in_forms():
    """Rotas /settings/providers/*/toggle alternam estado na UI e ocultam opções desativadas em /projects/new e /agents/new."""
    seed_database()
    client = TestClient(app)

    with SqlAlchemyUnitOfWork() as uow:
        orig_provider_settings = dict(uow.settings.get().provider_settings or {})

    try:
        # 1. Disable trello via Settings toggle route
        resp = client.post("/settings/providers/project/trello/toggle", follow_redirects=True)
        assert resp.status_code == 200
        assert "Provedor Trello desativado" in resp.text

        with SqlAlchemyUnitOfWork() as uow:
            assert not is_project_provider_enabled("trello", uow.settings.get().provider_settings)

        # /projects/new should omit disabled Trello option while keeping GitHub and Jira
        proj_form = client.get("/projects/new")
        assert proj_form.status_code == 200
        assert 'value="github"' in proj_form.text
        assert 'value="jira"' in proj_form.text
        assert 'value="trello"' not in proj_form.text

        # 2. Disable codex CLI via Settings toggle route
        resp_cli = client.post("/settings/providers/cli/codex/toggle", follow_redirects=True)
        assert resp_cli.status_code == 200
        assert "CLI OpenAI Codex CLI desativado" in resp_cli.text

        with SqlAlchemyUnitOfWork() as uow:
            assert not is_cli_provider_enabled("codex", uow.settings.get().provider_settings)

        # /agents/new should omit disabled codex option
        agent_form = client.get("/agents/new")
        assert agent_form.status_code == 200
        assert 'value="codex"' not in agent_form.text
        assert 'value="agy"' in agent_form.text

        # 3. Re-enable both via toggle routes
        resp_re1 = client.post("/settings/providers/project/trello/toggle", follow_redirects=True)
        assert resp_re1.status_code == 200
        assert "Provedor Trello ativado" in resp_re1.text

        resp_re2 = client.post("/settings/providers/cli/codex/toggle", follow_redirects=True)
        assert resp_re2.status_code == 200
        assert "CLI OpenAI Codex CLI ativado" in resp_re2.text
    finally:
        with SqlAlchemyUnitOfWork() as uow:
            uow.settings.update(provider_settings=orig_provider_settings)
            uow.commit()


def test_sqlite_legacy_project_provider_migration(tmp_path):
    """Bancos SQLite pré-existentes sem projects.project_provider migram herdando app_settings.active_project_provider."""
    db_file = tmp_path / "legacy_projects.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE app_settings (
            id INTEGER PRIMARY KEY,
            default_cli_provider VARCHAR NOT NULL,
            active_project_provider VARCHAR NOT NULL,
            provider_settings JSON NOT NULL,
            updated_at DATETIME NOT NULL
        );
        INSERT INTO app_settings (id, default_cli_provider, active_project_provider, provider_settings, updated_at)
        VALUES (1, 'gemini', 'jira', '{}', '2026-01-01 00:00:00');

        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            project_key VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            local_path VARCHAR NOT NULL,
            active BOOLEAN NOT NULL,
            last_run_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        INSERT INTO projects (id, project_key, name, local_path, active, created_at, updated_at)
        VALUES (1, 'ABC-1', 'Projeto Jira Legado', '/tmp', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        """
    )
    conn.close()

    legacy_engine = create_engine(f"sqlite:///{db_file}")
    init_db(legacy_engine)

    conn = sqlite3.connect(db_file)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    row = conn.execute("SELECT project_provider FROM projects WHERE id = 1").fetchone()
    conn.close()

    assert "project_provider" in cols
    assert row is not None
    assert row[0] == "jira"
