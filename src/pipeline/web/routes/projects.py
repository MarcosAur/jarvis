from collections import defaultdict
from pathlib import Path
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.orm_models import utc_now
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.bootstrap import project_registry
from pipeline.config import config
from pipeline.domain.ports.job_dispatcher import JobDispatcher
from pipeline.domain.provider_state import (
    get_disabled_project_providers,
    is_project_provider_enabled,
)
from pipeline.web.dependencies import get_job_dispatcher, get_orchestrator, get_uow

router = APIRouter(prefix="/projects", tags=["projects"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


def _project_provider_options(provider_settings: dict | None, current_key: str | None = None) -> list[dict]:
    options = []
    for pp in project_registry.list_all():
        enabled = is_project_provider_enabled(pp.provider_key, provider_settings)
        if enabled or pp.provider_key == current_key:
            options.append({"key": pp.provider_key, "name": pp.display_name, "enabled": enabled})
    return options


@router.get("", response_class=HTMLResponse)
def list_projects(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        projects = uow.projects.list_all()
        settings = uow.settings.get()
        disabled_providers = get_disabled_project_providers(settings.provider_settings)

    provider_labels = {pp.provider_key: pp.display_name for pp in project_registry.list_all()}

    return templates.TemplateResponse(
        request=request,
        name="projects/list.html",
        context={
            "active_page": "projects",
            "projects": projects,
            "provider_labels": provider_labels,
            "disabled_providers": disabled_providers,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_project_form(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        settings = uow.settings.get()
        project_providers = _project_provider_options(settings.provider_settings)

    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "active_page": "projects",
            "project": None,
            "project_providers": project_providers,
        },
    )


@router.post("/new")
def create_project(
    name: str = Form(...),
    project_provider: str = Form("github"),
    project_key: str = Form(...),
    local_path: str = Form(...),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    # Validate local path exists
    path = Path(local_path.strip()).expanduser()
    if not path.is_dir():
        return RedirectResponse(
            url=f"/projects?alert_message=O+diretório+informado+não+existe:+{local_path}&alert_type=error",
            status_code=303,
        )

    provider_key = (project_provider or "github").strip()
    if not project_registry.get_or_none(provider_key):
        return RedirectResponse(
            url=f"/projects?alert_message=Provedor+de+projeto+inválido:+{provider_key}&alert_type=error",
            status_code=303,
        )

    with uow:
        uow.projects.create(
            name=name.strip(),
            project_provider=provider_key,
            project_key=project_key.strip(),
            local_path=str(path.resolve()),
            active=active,
        )
        uow.commit()

    return RedirectResponse(url="/projects?alert_message=Projeto+criado+com+sucesso", status_code=303)


@router.get("/{project_id}/edit", response_class=HTMLResponse)
def edit_project_form(
    project_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        project = uow.projects.get_by_id(project_id)
        if not project:
            return RedirectResponse(url="/projects?alert_message=Projeto+não+encontrado&alert_type=error", status_code=303)
        settings = uow.settings.get()
        project_providers = _project_provider_options(settings.provider_settings, current_key=project.project_provider)

    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "active_page": "projects",
            "project": project,
            "project_providers": project_providers,
        },
    )


@router.post("/{project_id}/edit")
def update_project(
    project_id: int,
    name: str = Form(...),
    project_provider: str = Form("github"),
    project_key: str = Form(...),
    local_path: str = Form(...),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    path = Path(local_path.strip()).expanduser()
    if not path.is_dir():
        return RedirectResponse(
            url=f"/projects?alert_message=O+diretório+informado+não+existe:+{local_path}&alert_type=error",
            status_code=303,
        )

    provider_key = (project_provider or "github").strip()
    if not project_registry.get_or_none(provider_key):
        return RedirectResponse(
            url=f"/projects?alert_message=Provedor+de+projeto+inválido:+{provider_key}&alert_type=error",
            status_code=303,
        )

    with uow:
        uow.projects.update(
            project_id,
            name=name.strip(),
            project_provider=provider_key,
            project_key=project_key.strip(),
            local_path=str(path.resolve()),
            active=active,
        )
        uow.commit()

    return RedirectResponse(url="/projects?alert_message=Projeto+atualizado+com+sucesso", status_code=303)


@router.post("/{project_id}/toggle")
def toggle_project(
    project_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        project = uow.projects.get_by_id(project_id)
        if project:
            uow.projects.update(project_id, active=not project.active)
            uow.commit()

    return RedirectResponse(url="/projects", status_code=303)


@router.post("/{project_id}/delete")
def delete_project(
    project_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.projects.delete(project_id)
        uow.commit()

    return RedirectResponse(url="/projects?alert_message=Projeto+excluído+com+sucesso", status_code=303)


@router.post("/{project_id}/run")
def run_project_pipeline(
    project_id: int,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    run = orchestrator.run_for_project(project_id, trigger="web_project")
    if run.status == "ok":
        msg = f"Pipeline executada com sucesso! Cards sincronizados: {run.cards_synced}, Jobs enviados ao Celery: {run.jobs_created}"
        alert_type = "success"
    else:
        msg = f"Execução concluída com alerta/erro: {run.error}"
        alert_type = "error"

    return RedirectResponse(
        url=f"/projects/{project_id}/board?alert_message={msg}&alert_type={alert_type}",
        status_code=303,
    )


@router.post("/run-all")
def run_all_projects_pipeline(
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    runs = orchestrator.run_all_active(trigger="web_all")
    total_cards = sum(r.cards_synced for r in runs)
    total_jobs = sum(r.jobs_created for r in runs)
    msg = f"Pipeline rodou para {len(runs)} projeto(s). Total cards: {total_cards}, Jobs enviados ao Celery: {total_jobs}"
    return RedirectResponse(url=f"/projects?alert_message={msg}", status_code=303)


def _build_board_context(
    project_id: int,
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
) -> dict | None:
    worker_health = dispatcher.get_worker_health()

    with uow:
        project = uow.projects.get_by_id(project_id)
        if not project:
            return None

        settings = uow.settings.get()
        proj_provider_key = project.project_provider or "github"
        p_provider = project_registry.get_or_none(proj_provider_key)
        active_provider_name = p_provider.display_name if p_provider else proj_provider_key
        provider_enabled = is_project_provider_enabled(proj_provider_key, settings.provider_settings)

        raw_columns = uow.columns.list_all(active_only=True)
        columns = []
        for col in raw_columns:
            agent = uow.agents.get_by_id(col.agent_id) if col.agent_id else None
            columns.append({
                "id": col.id,
                "identifier": col.identifier,
                "column_name": col.column_name,
                "agent": agent,
                "next_column_name": col.next_column_name,
            })

        cards = uow.cards.list_by_project(project_id, include_removed=False)
        cards_by_column = defaultdict(list)
        rework_cards_count = 0
        for card in cards:
            cards_by_column[card.column_name.strip().lower()].append(card)
            if card.rework_count > 0:
                rework_cards_count += 1

        # Map latest job per card (list_all is ordered by desc(created_at))
        project_jobs = uow.jobs.list_all(project_id=project_id, limit=300)
        latest_job_by_card: dict[int, object] = {}
        running_count = 0
        pending_count = 0
        for j in project_jobs:
            if j.state == "running":
                running_count += 1
            elif j.state == "pending":
                pending_count += 1
            if j.card_id not in latest_job_by_card:
                latest_job_by_card[j.card_id] = j

        latest_job = project_jobs[0] if project_jobs else None
        last_event_text = None
        if latest_job:
            model_lbl = latest_job.model_id_snapshot or latest_job.cli_provider_snapshot or "agente"
            proc_lbl = latest_job.process_status or latest_job.state
            last_event_text = f"[Job #{latest_job.id} • {model_lbl}] {proc_lbl}"

    return {
        "active_page": "board",
        "project": project,
        "active_provider_name": active_provider_name,
        "active_provider_key": proj_provider_key,
        "provider_enabled": provider_enabled,
        "columns": columns,
        "cards_by_column": cards_by_column,
        "latest_job_by_card": latest_job_by_card,
        "total_cards": len(cards),
        "running_count": running_count,
        "pending_count": pending_count,
        "rework_cards_count": rework_cards_count,
        "worker_health": worker_health,
        "last_event_text": last_event_text,
        "pipeline_interval_seconds": config.CELERY_PIPELINE_INTERVAL_SECONDS,
        "now_utc": utc_now(),
    }


@router.get("/{project_id}/board", response_class=HTMLResponse)
def view_project_board(
    project_id: int,
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    context = _build_board_context(project_id=project_id, uow=uow, dispatcher=dispatcher)
    if context is None:
        return RedirectResponse(url="/projects?alert_message=Projeto+não+encontrado&alert_type=error", status_code=303)

    context["alert_message"] = alert_message
    context["alert_type"] = alert_type

    return templates.TemplateResponse(
        request=request,
        name="projects/board.html",
        context=context,
    )


@router.get("/{project_id}/board/partial", response_class=HTMLResponse)
def view_project_board_partial(
    project_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    context = _build_board_context(project_id=project_id, uow=uow, dispatcher=dispatcher)
    if context is None:
        return HTMLResponse("<p class='p-6 text-error'>Projeto não encontrado.</p>", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="projects/_board_content.html",
        context=context,
    )
