import uuid
from fastapi.testclient import TestClient
from pipeline.adapters.db.seed import seed_database
from pipeline.web.app import app


def test_cruds_end_to_end():
    seed_database()
    client = TestClient(app)
    uid = uuid.uuid4().hex[:6]

    # 1. Test Root Redirect
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)

    # ==================== CRUD 1: AGENTS ====================
    # List agents
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert "Arquiteto Gemini" in resp.text

    # Models options via HTMX
    resp = client.get("/agents/models-options?cli_provider=agy")
    assert resp.status_code == 200
    assert "<option" in resp.text

    # Create new agent
    agent_name = f"Desenvolvedor Claude {uid}"
    resp = client.post(
        "/agents/new",
        data={
            "name": agent_name,
            "cli_provider": "claude",
            "model_id": "claude-3-7-sonnet-latest",
            "prompt_markdown": "# Prompt Dev",
            "active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert agent_name in resp.text

    # ==================== CRUD 2: PROJECTS ====================
    # List projects
    resp = client.get("/projects")
    assert resp.status_code == 200

    # Create project (using /tmp as real directory)
    project_name = f"Projeto Web {uid}"
    project_key = f"test/{uid}"
    resp = client.post(
        "/projects/new",
        data={
            "name": project_name,
            "project_key": project_key,
            "local_path": "/tmp",
            "active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert project_name in resp.text

    # ==================== CRUD 3: COLUMNS ====================
    # List columns
    resp = client.get("/columns")
    assert resp.status_code == 200
    assert "To architect" in resp.text
    assert "Architected" in resp.text

    # Create new column
    col_name = f"Code Review {uid}"
    resp = client.post(
        "/columns/new",
        data={
            "column_name": col_name,
            "identifier": f"code_review_{uid}",
            "agent_id": "",
            "next_column_name": "Homolog",
            "order_index": "5",
            "active": "true",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert col_name in resp.text

    # ==================== CRUD 4: SETTINGS ====================
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Provedor CLI Padrão" in resp.text

    resp = client.post(
        "/settings",
        data={
            "default_cli_provider": "agy",
            "active_project_provider": "github",
            "github_token": "token123",
            "github_owner": "maurelio",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Configurações salvas com sucesso" in resp.text

    # ==================== CRUD 5: JOBS & RUNS ====================
    resp = client.get("/jobs")
    assert resp.status_code == 200

    resp = client.get("/runs")
    assert resp.status_code == 200


def test_agents_nexus_dashboard_and_cli_scan():
    seed_database()
    client = TestClient(app)

    resp = client.get("/agents")
    assert resp.status_code == 200
    assert "Agentes Ativos" in resp.text
    assert "Provedor Principal" in resp.text
    assert "CLIs no $PATH" in resp.text
    assert "CLIs no Ambiente Local" in resp.text
    assert "Modelos &amp; Limites do Worker" not in resp.text
    assert "Cadastrar Novo Agente de IA" in resp.text
    assert "To architect → Architected" in resp.text

    scan_resp = client.post("/agents/scan-clis")
    assert scan_resp.status_code == 200
    assert 'id="cli-status-panel"' in scan_resp.text
    assert "Varredura concluída:" in scan_resp.text

    form_resp = client.get("/agents/new")
    assert form_resp.status_code == 200
    assert "Novo Agente de IA" in form_resp.text


def test_nexus_columns_settings_runs_and_centered_navbar():
    seed_database()
    client = TestClient(app)

    # Top navbar geometric centralization
    cols_resp = client.get("/columns")
    assert cols_resp.status_code == 200
    assert "lg:left-1/2 lg:-translate-x-1/2" in cols_resp.text

    # Colunas do Fluxo
    assert "Visual Stepper da Esteira Autônoma" in cols_resp.text
    assert "Mapeamento e Orquestração de Colunas" in cols_resp.text
    assert "Simular Fluxo da Pipeline" in cols_resp.text
    assert "Nova Coluna" in cols_resp.text

    col_form_resp = client.get("/columns/new")
    assert col_form_resp.status_code == 200
    assert "Voltar para Colunas do Fluxo" in col_form_resp.text

    # Configurações Globais
    settings_resp = client.get("/settings")
    assert settings_resp.status_code == 200
    assert "Provedores &amp; Ambientes Padrão" in settings_resp.text
    assert "Provedor CLI Padrão" in settings_resp.text
    assert "Credenciais dos Provedores de Projetos" in settings_resp.text
    assert 'form="sync-models-form"' in settings_resp.text

    # Histórico de Execuções & Auditoria
    runs_resp = client.get("/runs?range=all&project_id=&agent_id=&status=all&q=")
    assert runs_resp.status_code == 200
    assert "Histórico de Execuções &amp; Auditoria" in runs_resp.text
    assert "Trilhas de Execução Recentes" in runs_resp.text
    assert "Rodadas do Orquestrador (Sync / Beat)" in runs_resp.text
    assert 'id="audit-inspector"' in runs_resp.text

    # Export JSON & CSV
    export_json = client.get("/runs/export?format=json")
    assert export_json.status_code == 200
    assert "application/json" in export_json.headers.get("content-type", "")
    assert "ai-pipeline-audit.json" in export_json.headers.get("content-disposition", "")
    assert export_json.json() is not None

    export_csv = client.get("/runs/export?format=csv")
    assert export_csv.status_code == 200
    assert "text/csv" in export_csv.headers.get("content-type", "")
    assert "ai-pipeline-audit.csv" in export_csv.headers.get("content-disposition", "")

    # Detail Inspector & filtered runs view with real job
    import uuid
    from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork

    uid = uuid.uuid4().hex[:6]
    with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.create(
            project_key=f"audit-proj-{uid}",
            name=f"Projeto Audit {uid}",
            local_path="/tmp",
            active=True,
        )
        card = uow.cards.create(
            project_id=proj.id,
            remote_id=f"aud-{uid}",
            title=f"Card Auditoria {uid}",
            body="Body auditoria",
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
            state="done",
        )
        uow.jobs.update(job.id, output_summary=f"Log audit preview {uid}")
        uow.commit()
        proj_id = proj.id
        job_id = job.id

    filtered_runs = client.get(f"/runs?range=all&project_id={proj_id}&status=done&q={uid}")
    assert filtered_runs.status_code == 200
    assert f"Card Auditoria {uid}" in filtered_runs.text
    assert f"Log audit preview {uid}" in filtered_runs.text

    inspector_resp = client.get(f"/runs/inspector/{job_id}")
    assert inspector_resp.status_code == 200
    assert 'id="audit-inspector"' in inspector_resp.text
    assert f"Card Auditoria {uid}" in inspector_resp.text
    assert f"Log audit preview {uid}" in inspector_resp.text

    # /jobs/new Nexus design & dynamic project card filtering
    new_job_resp = client.get(f"/jobs/new?project_id={proj_id}")
    assert new_job_resp.status_code == 200
    assert "Enfileirar Execução Manual de Agente" in new_job_resp.text
    assert "Snapshot do Despacho" in new_job_resp.text
    assert "Limites de Execução (SLA)" in new_job_resp.text
    assert f"Card Auditoria {uid}" in new_job_resp.text

