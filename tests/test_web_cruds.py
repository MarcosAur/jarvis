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
