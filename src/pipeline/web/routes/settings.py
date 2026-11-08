from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.web.dependencies import get_model_catalog_service, get_uow

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


@router.get("", response_class=HTMLResponse)
def get_settings(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        settings = uow.settings.get()

    cli_providers = [
        {"key": p.provider_key, "name": p.display_name, "binary_name": p.binary_name, "installed": p.is_installed()}
        for p in cli_registry.list_all()
    ]

    project_providers = [
        {"key": pp.provider_key, "name": pp.display_name}
        for pp in project_registry.list_all()
    ]

    return templates.TemplateResponse(
        request=request,
        name="settings/form.html",
        context={
            "active_page": "settings",
            "settings": settings,
            "provider_settings": settings.provider_settings or {},
            "cli_providers": cli_providers,
            "project_providers": project_providers,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.post("")
def update_settings(
    default_cli_provider: str = Form(...),
    active_project_provider: str = Form(...),
    github_token: str | None = Form(None),
    github_owner: str | None = Form(None),
    jira_base_url: str | None = Form(None),
    jira_email: str | None = Form(None),
    jira_api_token: str | None = Form(None),
    trello_api_key: str | None = Form(None),
    trello_token: str | None = Form(None),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        current_settings = uow.settings.get()
        p_settings = dict(current_settings.provider_settings or {})

        if github_token is not None:
            p_settings["github_token"] = github_token.strip()
        if github_owner is not None:
            p_settings["github_owner"] = github_owner.strip()

        if jira_base_url is not None:
            p_settings["jira_base_url"] = jira_base_url.strip()
        if jira_email is not None:
            p_settings["jira_email"] = jira_email.strip()
        if jira_api_token is not None:
            p_settings["jira_api_token"] = jira_api_token.strip()

        if trello_api_key is not None:
            p_settings["trello_api_key"] = trello_api_key.strip()
        if trello_token is not None:
            p_settings["trello_token"] = trello_token.strip()

        uow.settings.update(
            default_cli_provider=default_cli_provider.strip(),
            active_project_provider=active_project_provider.strip(),
            provider_settings=p_settings,
        )
        uow.commit()

    return RedirectResponse(url="/settings?alert_message=Configurações+salvas+com+sucesso", status_code=303)


@router.post("/sync-models")
def sync_all_cli_models(
    catalog: ModelCatalogService = Depends(get_model_catalog_service),
):
    results = catalog.sync_all_installed_providers()
    summary = ", ".join([f"{k}: {v} modelos" for k, v in results.items() if v > 0])
    msg = f"Modelos sincronizados com sucesso! ({summary})" if summary else "Nenhum modelo novo encontrado nas CLIs instaladas."
    return RedirectResponse(url=f"/settings?alert_message={msg}", status_code=303)
