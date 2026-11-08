from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.bootstrap import cli_registry
from pipeline.web.dependencies import get_model_catalog_service, get_uow

router = APIRouter(prefix="/agents", tags=["agents"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


@router.get("", response_class=HTMLResponse)
def list_agents(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        agents = uow.agents.list_all()

    return templates.TemplateResponse(
        request=request,
        name="agents/list.html",
        context={
            "active_page": "agents",
            "agents": agents,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_agent_form(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        settings = uow.settings.get()
        default_cli = settings.default_cli_provider
        # Fetch models for default CLI from DB
        models = uow.models.list_by_provider(default_cli)

    # List registered CLI providers with installation status
    cli_providers = [
        {"key": p.provider_key, "name": p.display_name, "installed": p.is_installed()}
        for p in cli_registry.list_all()
    ]

    return templates.TemplateResponse(
        request=request,
        name="agents/form.html",
        context={
            "active_page": "agents",
            "agent": None,
            "cli_providers": cli_providers,
            "default_cli": default_cli,
            "models": models,
        },
    )


@router.post("/new")
def create_agent(
    name: str = Form(...),
    cli_provider: str = Form(...),
    model_id: str = Form(...),
    prompt_markdown: str = Form(""),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.agents.create(
            name=name.strip(),
            cli_provider=cli_provider.strip(),
            model_id=model_id.strip(),
            prompt_markdown=prompt_markdown,
            active=active,
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
        models = uow.models.list_by_provider(agent.cli_provider)

    cli_providers = [
        {"key": p.provider_key, "name": p.display_name, "installed": p.is_installed()}
        for p in cli_registry.list_all()
    ]

    return templates.TemplateResponse(
        request=request,
        name="agents/form.html",
        context={
            "active_page": "agents",
            "agent": agent,
            "cli_providers": cli_providers,
            "default_cli": agent.cli_provider,
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
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.agents.update(
            agent_id,
            name=name.strip(),
            cli_provider=cli_provider.strip(),
            model_id=model_id.strip(),
            prompt_markdown=prompt_markdown,
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
        # Check if any active FlowColumn uses this agent
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

    # If no cached models found, attempt dynamic sync
    if not models:
        raw_models = catalog.sync_models_for_provider(cli_provider)
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
