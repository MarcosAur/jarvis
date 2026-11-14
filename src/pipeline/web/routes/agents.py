import shutil
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.bootstrap import cli_registry
from pipeline.domain.provider_state import is_cli_provider_enabled
from pipeline.web.dependencies import get_model_catalog_service, get_uow

router = APIRouter(prefix="/agents", tags=["agents"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")

_JOB_STATE_LABELS = {
    "done": "Sucesso",
    "running": "Em execução",
    "pending": "Na fila",
    "failed": "Falhou",
    "cancelled": "Cancelado",
}


def _collect_cli_statuses(
    uow: SqlAlchemyUnitOfWork,
    provider_settings: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cli_statuses: list[dict[str, Any]] = []
    cli_provider_map: dict[str, dict[str, Any]] = {}

    for provider in cli_registry.list_all():
        installed = provider.is_installed()
        enabled = is_cli_provider_enabled(provider.provider_key, provider_settings)
        binary_path = shutil.which(provider.binary_name)
        cached_models = uow.models.list_by_provider(provider.provider_key)
        item: dict[str, Any] = {
            "key": provider.provider_key,
            "name": provider.display_name,
            "binary_name": provider.binary_name,
            "binary_path": binary_path,
            "installed": installed,
            "enabled": enabled,
            "models_count": len(cached_models),
        }
        cli_statuses.append(item)
        cli_provider_map[provider.provider_key] = item

    return cli_statuses, cli_provider_map


def _pick_initial_cli(cli_statuses: list[dict[str, Any]]) -> str:
    for item in cli_statuses:
        if item["enabled"] and item["installed"]:
            return str(item["key"])
    for item in cli_statuses:
        if item["enabled"]:
            return str(item["key"])
    return str(cli_statuses[0]["key"]) if cli_statuses else "agy"


def _summarize_prompt(prompt_markdown: str, max_len: int = 115) -> str:
    for raw_line in (prompt_markdown or "").splitlines():
        cleaned = raw_line.strip().lstrip("#*-`> ").strip()
        if cleaned:
            if len(cleaned) > max_len:
                return f"{cleaned[: max_len - 1]}…"
            return cleaned
    return "Sem descrição no prompt de sistema configurado."


def _build_agents_dashboard_context(uow: SqlAlchemyUnitOfWork) -> dict[str, Any]:
    app_settings = uow.settings.get()
    agents = uow.agents.list_all()
    columns = uow.columns.list_all()
    jobs = uow.jobs.list_all(limit=500)

    cli_statuses, cli_provider_map = _collect_cli_statuses(uow, app_settings.provider_settings)
    initial_cli_key = _pick_initial_cli(cli_statuses)
    default_models = uow.models.list_by_provider(initial_cli_key)

    columns_by_agent: dict[int, list[dict[str, Any]]] = {}
    for col in columns:
        if col.agent_id is None:
            continue
        columns_by_agent.setdefault(col.agent_id, []).append(
            {
                "id": col.id,
                "column_name": col.column_name,
                "next_column_name": col.next_column_name,
                "active": col.active,
            }
        )

    jobs_by_agent: dict[int, list[Any]] = {}
    for job in jobs:
        if job.agent_id is not None:
            jobs_by_agent.setdefault(job.agent_id, []).append(job)

    agent_cards: list[dict[str, Any]] = []

    for agent in agents:
        agent_jobs = jobs_by_agent.get(agent.id, []) if agent.id is not None else []
        running_job = next((j for j in agent_jobs if j.state == "running"), None)
        last_job = agent_jobs[0] if agent_jobs else None

        done_jobs = sum(1 for j in agent_jobs if j.state == "done")
        failed_jobs = sum(1 for j in agent_jobs if j.state == "failed")
        finished_count = done_jobs + failed_jobs
        approval_rate = round((done_jobs / finished_count) * 100) if finished_count > 0 else None

        durations = [
            max((j.finished_at - j.started_at).total_seconds(), 0.0)
            for j in agent_jobs
            if j.started_at is not None and j.finished_at is not None and j.state in ("done", "failed")
        ]
        avg_duration_s = round(sum(durations) / len(durations), 1) if durations else None

        provider_info = cli_provider_map.get(agent.cli_provider)
        linked_cols = columns_by_agent.get(agent.id, []) if agent.id is not None else []

        running_jobs_count = sum(1 for j in agent_jobs if j.state == "running")

        agent_cards.append(
            {
                "agent": agent,
                "prompt_summary": _summarize_prompt(agent.prompt_markdown),
                "provider_display": provider_info["name"] if provider_info else agent.cli_provider.upper(),
                "provider_installed": provider_info["installed"] if provider_info else False,
                "provider_enabled": provider_info["enabled"] if provider_info else True,
                "linked_columns": linked_cols,
                "running_job": running_job,
                "running_jobs_count": running_jobs_count,
                "last_job": last_job,
                "last_job_state_label": _JOB_STATE_LABELS.get(last_job.state, last_job.state) if last_job else None,
                "total_jobs": len(agent_jobs),
                "done_jobs": done_jobs,
                "failed_jobs": failed_jobs,
                "approval_rate": approval_rate,
                "avg_duration_s": avg_duration_s,
            }
        )

    total_agents = len(agents)
    active_agents = sum(1 for a in agents if a.active)
    installed_clis = sum(1 for c in cli_statuses if c["installed"])
    missing_clis = len(cli_statuses) - installed_clis
    enabled_clis = sum(1 for c in cli_statuses if c["enabled"])
    total_models_count = sum(int(c["models_count"]) for c in cli_statuses if c["enabled"])

    return {
        "active_page": "agents",
        "agents": agents,
        "agent_cards": agent_cards,
        "cli_providers": cli_statuses,
        "initial_cli": initial_cli_key,
        "default_models": default_models,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "installed_clis": installed_clis,
        "missing_clis": missing_clis,
        "enabled_clis": enabled_clis,
        "total_models_count": total_models_count,
    }


@router.get("", response_class=HTMLResponse)
def list_agents(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        context = _build_agents_dashboard_context(uow)

    context["alert_message"] = alert_message
    context["alert_type"] = alert_type

    return templates.TemplateResponse(
        request=request,
        name="agents/list.html",
        context=context,
    )


@router.post("/scan-clis", response_class=HTMLResponse)
def scan_clis_panel(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        app_settings = uow.settings.get()
        cli_statuses, _ = _collect_cli_statuses(uow, app_settings.provider_settings)

    installed_clis = sum(1 for c in cli_statuses if c["installed"])
    return templates.TemplateResponse(
        request=request,
        name="agents/_cli_panel.html",
        context={
            "cli_providers": cli_statuses,
            "installed_clis": installed_clis,
            "scan_completed": True,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_agent_form(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        settings = uow.settings.get()
        cli_statuses, _ = _collect_cli_statuses(uow, settings.provider_settings)
        initial_cli = _pick_initial_cli(cli_statuses)
        models = uow.models.list_by_provider(initial_cli)

    cli_providers = [c for c in cli_statuses if c["enabled"]]

    return templates.TemplateResponse(
        request=request,
        name="agents/form.html",
        context={
            "active_page": "agents",
            "agent": None,
            "cli_providers": cli_providers,
            "initial_cli": initial_cli,
            "models": models,
        },
    )


@router.post("/new")
def create_agent(
    name: str = Form(...),
    cli_provider: str = Form(...),
    model_id: str = Form(...),
    prompt_markdown: str = Form(""),
    max_parallel_executions: int = Form(1),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    safe_parallel = max(1, min(int(max_parallel_executions), 32))
    with uow:
        uow.agents.create(
            name=name.strip(),
            cli_provider=cli_provider.strip(),
            model_id=model_id.strip(),
            prompt_markdown=prompt_markdown,
            active=active,
            max_parallel_executions=safe_parallel,
        )
        uow.commit()

    return RedirectResponse(url="/agents?alert_message=Agente+criado+com+sucesso", status_code=303)


@router.get("/{agent_id}/edit", response_class=HTMLResponse)
def edit_agent_form(
    agent_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        agent = uow.agents.get_by_id(agent_id)
        if not agent:
            return RedirectResponse(url="/agents?alert_message=Agente+não+encontrado&alert_type=error", status_code=303)
        settings = uow.settings.get()
        cli_statuses, _ = _collect_cli_statuses(uow, settings.provider_settings)
        models = uow.models.list_by_provider(agent.cli_provider)

    cli_providers = [c for c in cli_statuses if c["enabled"] or c["key"] == agent.cli_provider]

    return templates.TemplateResponse(
        request=request,
        name="agents/form.html",
        context={
            "active_page": "agents",
            "agent": agent,
            "cli_providers": cli_providers,
            "initial_cli": agent.cli_provider,
            "models": models,
        },
    )


@router.post("/{agent_id}/edit")
def update_agent(
    agent_id: int,
    name: str = Form(...),
    cli_provider: str = Form(...),
    model_id: str = Form(...),
    prompt_markdown: str = Form(""),
    max_parallel_executions: int = Form(1),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    safe_parallel = max(1, min(int(max_parallel_executions), 32))
    with uow:
        uow.agents.update(
            agent_id,
            name=name.strip(),
            cli_provider=cli_provider.strip(),
            model_id=model_id.strip(),
            prompt_markdown=prompt_markdown,
            max_parallel_executions=safe_parallel,
            active=active,
        )
        uow.commit()

    return RedirectResponse(url="/agents?alert_message=Agente+atualizado+com+sucesso", status_code=303)


@router.post("/{agent_id}/toggle")
def toggle_agent(
    agent_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        agent = uow.agents.get_by_id(agent_id)
        if agent:
            uow.agents.update(agent_id, active=not agent.active)
            uow.commit()

    return RedirectResponse(url="/agents", status_code=303)


@router.post("/{agent_id}/delete")
def delete_agent(
    agent_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        linked_columns = [
            c for c in uow.columns.list_all(active_only=True) if c.agent_id == agent_id
        ]
        if linked_columns:
            col_names = ", ".join([c.column_name for c in linked_columns])
            return RedirectResponse(
                url=f"/agents?alert_message=Não+é+possível+excluir+o+agente+vinculado+às+colunas+ativas:+{col_names}&alert_type=error",
                status_code=303,
            )

        uow.agents.delete(agent_id)
        uow.commit()

    return RedirectResponse(url="/agents?alert_message=Agente+excluído+com+sucesso", status_code=303)


@router.get("/models-options", response_class=HTMLResponse)
def get_models_options(
    cli_provider: str,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    catalog: ModelCatalogService = Depends(get_model_catalog_service),
):
    with uow:
        models = uow.models.list_by_provider(cli_provider)

    if not models:
        catalog.sync_models_for_provider(cli_provider)
        with uow:
            models = uow.models.list_by_provider(cli_provider)

    return templates.TemplateResponse(
        request=request,
        name="agents/models_options.html",
        context={"models": models, "selected_model": None},
    )


@router.post("/sync-models", response_class=HTMLResponse)
def sync_models_endpoint(
    request: Request,
    cli_provider: str = Form(...),
    catalog: ModelCatalogService = Depends(get_model_catalog_service),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    catalog.sync_models_for_provider(cli_provider)
    with uow:
        models = uow.models.list_by_provider(cli_provider)

    return templates.TemplateResponse(
        request=request,
        name="agents/models_options.html",
        context={"models": models, "selected_model": None},
    )
