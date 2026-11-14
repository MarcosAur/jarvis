from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.config import config
from pipeline.domain.provider_state import (
    get_disabled_cli_providers,
    is_cli_provider_enabled,
    is_project_provider_enabled,
    set_cli_provider_enabled,
    set_project_provider_enabled,
)
from pipeline.web.dependencies import get_model_catalog_service, get_uow

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


def _has_project_credentials(provider_key: str, provider_settings: dict) -> bool:
    ps = provider_settings or {}
    if provider_key == "github":
        return bool(ps.get("github_token") or config.GITHUB_TOKEN)
    if provider_key == "jira":
        return bool((ps.get("jira_base_url") or config.JIRA_BASE_URL) and (ps.get("jira_api_token") or config.JIRA_API_TOKEN))
    if provider_key == "trello":
        return bool((ps.get("trello_api_key") or config.TRELLO_API_KEY) and (ps.get("trello_token") or config.TRELLO_TOKEN))
    return False


@router.get("", response_class=HTMLResponse)
def get_settings(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        settings = uow.settings.get()
        p_settings = dict(settings.provider_settings or {})

        cli_providers = [
            {
                "key": p.provider_key,
                "name": p.display_name,
                "binary_name": p.binary_name,
                "installed": p.is_installed(),
                "enabled": is_cli_provider_enabled(p.provider_key, p_settings),
                "models_count": len(uow.models.list_by_provider(p.provider_key)),
            }
            for p in cli_registry.list_all()
        ]

        project_providers = [
            {
                "key": pp.provider_key,
                "name": pp.display_name,
                "enabled": is_project_provider_enabled(pp.provider_key, p_settings),
                "configured": _has_project_credentials(pp.provider_key, p_settings),
            }
            for pp in project_registry.list_all()
        ]

    return templates.TemplateResponse(
        request=request,
        name="settings/form.html",
        context={
            "active_page": "settings",
            "settings": settings,
            "provider_settings": p_settings,
            "cli_providers": cli_providers,
            "project_providers": project_providers,
            "enabled_cli_count": sum(1 for c in cli_providers if c["enabled"]),
            "enabled_project_count": sum(1 for p in project_providers if p["enabled"]),
            "cli_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
            "celery_interval_seconds": config.CELERY_PIPELINE_INTERVAL_SECONDS,
            "celery_soft_timeout_seconds": config.celery_soft_time_limit,
            "celery_hard_timeout_seconds": config.celery_time_limit,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.post("")
def update_settings(
    default_cli_provider: str | None = Form(None),
    active_project_provider: str | None = Form(None),
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
            default_cli_provider=default_cli_provider.strip() if default_cli_provider else None,
            active_project_provider=active_project_provider.strip() if active_project_provider else None,
            provider_settings=p_settings,
        )
        uow.commit()

    return RedirectResponse(url="/settings?alert_message=Configurações+salvas+com+sucesso", status_code=303)


@router.post("/providers/project/{provider_key}/toggle")
def toggle_project_provider(
    provider_key: str,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    provider = project_registry.get_or_none(provider_key)
    if not provider:
        return RedirectResponse(url="/settings?alert_message=Provedor+de+projeto+não+encontrado&alert_type=error", status_code=303)

    with uow:
        settings = uow.settings.get()
        p_settings = dict(settings.provider_settings or {})
        new_enabled = not is_project_provider_enabled(provider_key, p_settings)
        updated_settings = set_project_provider_enabled(p_settings, provider_key, new_enabled)
        uow.settings.update(provider_settings=updated_settings)
        uow.commit()

    state_lbl = "ativado" if new_enabled else "desativado"
    return RedirectResponse(url=f"/settings?alert_message=Provedor+{provider.display_name}+{state_lbl}", status_code=303)


@router.post("/providers/cli/{provider_key}/toggle")
def toggle_cli_provider(
    provider_key: str,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    provider = cli_registry.get_or_none(provider_key)
    if not provider:
        return RedirectResponse(url="/settings?alert_message=Provedor+CLI+não+encontrado&alert_type=error", status_code=303)

    with uow:
        settings = uow.settings.get()
        p_settings = dict(settings.provider_settings or {})
        new_enabled = not is_cli_provider_enabled(provider_key, p_settings)
        updated_settings = set_cli_provider_enabled(p_settings, provider_key, new_enabled)
        uow.settings.update(provider_settings=updated_settings)
        uow.commit()

    state_lbl = "ativado" if new_enabled else "desativado"
    return RedirectResponse(url=f"/settings?alert_message=CLI+{provider.display_name}+{state_lbl}", status_code=303)


@router.post("/sync-models")
def sync_all_cli_models(
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    catalog: ModelCatalogService = Depends(get_model_catalog_service),
):
    with uow:
        settings = uow.settings.get()
        disabled = get_disabled_cli_providers(settings.provider_settings)

    results = catalog.sync_all_installed_providers(disabled_providers=disabled)
    summary = ", ".join([f"{k}: {v} modelos" for k, v in results.items() if v > 0])
    msg = f"Modelos sincronizados com sucesso! ({summary})" if summary else "Nenhum modelo novo encontrado nas CLIs ativas e instaladas."
    return RedirectResponse(url=f"/settings?alert_message={msg}", status_code=303)
