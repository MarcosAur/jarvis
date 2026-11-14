from collections import defaultdict
from pathlib import Path
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.bootstrap import project_registry
from pipeline.web.dependencies import get_orchestrator, get_uow

router = APIRouter(prefix="/projects", tags=["projects"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


@router.get("", response_class=HTMLResponse)
def list_projects(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        projects = uow.projects.list_all()

    return templates.TemplateResponse(
        request=request,
        name="projects/list.html",
        context={
            "active_page": "projects",
            "projects": projects,
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
        p_provider = project_registry.get_or_none(settings.active_project_provider)
        active_provider_name = p_provider.display_name if p_provider else settings.active_project_provider

    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "active_page": "projects",
            "project": None,
            "active_provider_name": active_provider_name,
        },
    )


@router.post("/new")
def create_project(
    name: str = Form(...),
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

    with uow:
        uow.projects.create(
            name=name.strip(),
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
        p_provider = project_registry.get_or_none(settings.active_project_provider)
        active_provider_name = p_provider.display_name if p_provider else settings.active_project_provider

    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "active_page": "projects",
            "project": project,
            "active_provider_name": active_provider_name,
        },
    )


@router.post("/{project_id}/edit")
def update_project(
    project_id: int,
    name: str = Form(...),
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

    with uow:
        uow.projects.update(
            project_id,
            name=name.strip(),
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


@router.get("/{project_id}/board", response_class=HTMLResponse)
def view_project_board(
    project_id: int,
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        project = uow.projects.get_by_id(project_id)
        if not project:
            return RedirectResponse(url="/projects?alert_message=Projeto+não+encontrado&alert_type=error", status_code=303)

        raw_columns = uow.columns.list_all(active_only=True)
        # Attach agent objects
        columns = []
        for col in raw_columns:
            agent = uow.agents.get_by_id(col.agent_id) if col.agent_id else None
            columns.append({"id": col.id, "column_name": col.column_name, "agent": agent, "next_column_name": col.next_column_name})

        cards = uow.cards.list_by_project(project_id, include_removed=False)
        cards_by_column = defaultdict(list)
        for card in cards:
            cards_by_column[card.column_name.strip().lower()].append(card)

    return templates.TemplateResponse(
        request=request,
        name="projects/board.html",
        context={
            "active_page": "projects",
            "project": project,
            "columns": columns,
            "cards_by_column": cards_by_column,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )
