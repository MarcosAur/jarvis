from sqlmodel import create_engine
from pipeline.adapters.db.engine import init_db
from pipeline.adapters.db.seed import seed_database
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.job_runner_service import JobRunnerService
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.application.sync_service import SyncService
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.domain.entities import RemoteCard
from tests.fakes import FakeCliProvider, FakeProjectProvider


def test_orchestrator_syncs_cards_and_enqueues_jobs():
    # Setup in-memory db
    mem_engine = create_engine("sqlite:///:memory:")
    init_db(mem_engine)

    def uow_factory():
        return SqlAlchemyUnitOfWork(lambda: mem_engine.connect())

    # We need Session tied to mem_engine
    from sqlmodel import Session
    uow_fact = lambda: SqlAlchemyUnitOfWork(lambda: Session(mem_engine, expire_on_commit=False))
    seed_database(uow_fact())

    # Register fake providers
    fake_cli = FakeCliProvider()
    cli_registry.register(fake_cli)

    remote_cards = [
        RemoteCard(remote_id="card-1", title="Card em Todo", body="Sem agente", column_name="Todo"),
        RemoteCard(remote_id="card-2", title="Card de Arquitetura", body="Criar contratos", column_name="To architect"),
    ]
    fake_board = FakeProjectProvider(remote_cards)
    project_registry.register(fake_board)

    # Configure active project provider to fake_board
    with uow_fact() as uow:
        uow.settings.update(
            default_cli_provider="fake_cli",
            active_project_provider="fake_board",
            provider_settings={},
        )
        proj = uow.projects.create(
            project_key="fake-proj-1",
            project_provider="fake_board",
            name="Projeto Teste",
            local_path="/tmp",
            active=True,
        )
        uow.commit()
        project_id = proj.id

    # Run orchestrator
    orchestrator = PipelineOrchestrator(uow_fact, SyncService())
    run = orchestrator.run_for_project(project_id)

    assert run.status == "ok"
    assert run.cards_synced == 2
    assert run.jobs_created == 1  # only card-2 in "To architect" has an agent

    with uow_fact() as uow:
        jobs = uow.jobs.list_all(project_id=project_id)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.state == "pending"
        assert job.target_column_snapshot == "Architected"

        card2 = uow.cards.get_by_remote_id(project_id, "card-2")
        assert card2 is not None
        assert card2.rework_count == 0

    # Execute the job in dry-run
    runner = JobRunnerService(uow_fact)
    res = runner.run_job(job.id, dry_run=True)
    assert res["success"] is True

    with uow_fact() as uow:
        job_updated = uow.jobs.get_by_id(job.id)
        assert job_updated.state == "succeeded"
        assert "[Simulação Dry-Run]" in job_updated.output_summary

    # Test Live execution (dry_run=False) with FakeCliProvider
    with uow_fact() as uow:
        live_job = uow.jobs.create(
            project_id=project_id,
            card_id=card2.id,
            flow_column_id=job.flow_column_id,
            agent_id=job.agent_id,
            cli_provider_snapshot="fake_cli",
            model_id_snapshot="fake-model-1",
            target_column_snapshot="Architected",
            state="pending",
        )
        uow.commit()
        live_job_id = live_job.id

    res_live = runner.run_job(live_job_id, dry_run=False)
    assert res_live["success"] is True
    assert "fake prompt" in res_live["output"]

    with uow_fact() as uow:
        job_live_db = uow.jobs.get_by_id(live_job_id)
        assert job_live_db.state == "succeeded"
        assert "fake prompt" in job_live_db.output_summary


def test_rework_detection_when_card_moves_back():
    mem_engine = create_engine("sqlite:///:memory:")
    init_db(mem_engine)
    from sqlmodel import Session
    uow_fact = lambda: SqlAlchemyUnitOfWork(lambda: Session(mem_engine, expire_on_commit=False))
    seed_database(uow_fact())

    with uow_fact() as uow:
        proj = uow.projects.create(
            project_key="proj-rework",
            name="Projeto Rework",
            local_path="/tmp",
            active=True,
        )
        uow.commit()
        p_id = proj.id

    sync = SyncService()

    # Step 1: Card arrives in "Architected" (order index 3)
    c1 = RemoteCard(remote_id="card-rw", title="Feature X", body="Desc", column_name="Architected")
    with uow_fact() as uow:
        sync.sync_cards(p_id, [c1], uow)
        uow.commit()

        card = uow.cards.get_by_remote_id(p_id, "card-rw")
        assert card.column_name == "Architected"
        assert card.rework_count == 0

    # Step 2: Card returned back to "To architect" (order index 2 < 3) -> Rework!
    c2 = RemoteCard(remote_id="card-rw", title="Feature X", body="Desc", column_name="To architect")
    with uow_fact() as uow:
        sync.sync_cards(p_id, [c2], uow)
        uow.commit()

        card = uow.cards.get_by_remote_id(p_id, "card-rw")
        assert card.column_name == "To architect"
        assert card.rework_count == 1

        events = uow.events.list_by_card(card.id)
        assert any(e.is_rework for e in events)
