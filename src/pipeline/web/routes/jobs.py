import logging
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.orm_models import utc_now
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.config import config
from pipeline.domain.ports.job_dispatcher import JobDispatcher
from pipeline.web.dependencies import get_job_dispatcher, get_uow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


def _dispatch_job_to_celery(
    job_id: int,
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
) -> tuple[bool, str | None]:
    """Dispatch a pending job to Celery and persist its task ID / process status."""
    try:
        task_id = dispatcher.dispatch_job(job_id)
        with uow:
            current = uow.jobs.get_by_id(job_id)
            if current:
                updates: dict = {}
                if task_id and not current.celery_task_id:
                    updates["celery_task_id"] = task_id
                if current.state == "pending":
                    updates["process_status"] = (
                        "Na fila do Celery" if task_id else "Pendente (aguardando envio ao Celery)"
                    )
                if updates:
                    uow.jobs.update(job_id, **updates)
                    uow.commit()
        return True, task_id
    except Exception as exc:
        logger.warning("Falha ao enviar Job #%s ao Celery: %s", job_id, exc)
        with uow:
            current = uow.jobs.get_by_id(job_id)
            if current and current.state == "pending":
                uow.jobs.update(job_id, process_status="Pendente (broker Celery indisponível)")
                uow.commit()
        return False, None


def _build_jobs_list_context(
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
    project_id: int | None = None,
    state: str | None = None,
) -> dict:
    worker_health = dispatcher.get_worker_health()

    with uow:
        projects = uow.projects.list_all()
        proj_map = {p.id: p for p in projects}
        agents = uow.agents.list_all()
        agent_map = {a.id: a for a in agents}
        columns = uow.columns.list_all()
        col_map = {c.id: c for c in columns}

        raw_jobs = uow.jobs.list_all(project_id=project_id, state=state if state else None)
        jobs = []
        for j in raw_jobs:
            card = uow.cards.get_by_id(j.card_id)
            proj = proj_map.get(j.project_id)
            agent = agent_map.get(j.agent_id)
            col = col_map.get(j.flow_column_id)

            celery_state = None
            if j.celery_task_id and worker_health.broker_available and j.state in ("pending", "running"):
                celery_state = dispatcher.get_task_status(j.celery_task_id).state

            jobs.append({
                "id": j.id,
                "project_name": proj.name if proj else f"Projeto #{j.project_id}",
                "card_title": card.title if card else f"Card #{j.card_id}",
                "card_issue": card.issue_number if card else None,
                "column_name": col.column_name if col else "Desconhecida",
                "agent_name": agent.name if agent else "Nenhum",
                "cli_provider_snapshot": j.cli_provider_snapshot or "—",
                "model_id_snapshot": j.model_id_snapshot or "—",
                "state": j.state,
                "celery_task_id": j.celery_task_id,
                "celery_state": celery_state,
                "process_status": j.process_status or "—",
                "created_at": j.created_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            })

    return {
        "active_page": "jobs",
        "jobs": jobs,
        "projects": projects,
        "selected_project_id": project_id,
        "selected_state": state,
        "worker_health": worker_health,
        "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
        "celery_soft_timeout_seconds": config.celery_soft_time_limit,
        "celery_hard_timeout_seconds": config.celery_time_limit,
        "pipeline_interval_seconds": config.CELERY_PIPELINE_INTERVAL_SECONDS,
    }


def _build_job_detail_context(
    job_id: int,
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
) -> dict | None:
    worker_health = dispatcher.get_worker_health()

    with uow:
        job = uow.jobs.get_by_id(job_id)
        if not job:
            return None

        project = uow.projects.get_by_id(job.project_id)
        card = uow.cards.get_by_id(job.card_id)
        agent = uow.agents.get_by_id(job.agent_id) if job.agent_id else None
        column = uow.columns.get_by_id(job.flow_column_id)
        card_events = uow.events.list_by_card(job.card_id) if job.card_id else []

    celery_status = None
    if job.celery_task_id:
        if worker_health.broker_available:
            celery_status = dispatcher.get_task_status(job.celery_task_id)
        else:
            from pipeline.domain.ports.job_dispatcher import CeleryTaskStatus

            celery_status = CeleryTaskStatus(
                task_id=job.celery_task_id,
                state="BROKER_OFFLINE",
                detail=worker_health.error,
            )

    return {
        "active_page": "jobs",
        "job": job,
        "project": project,
        "card": card,
        "agent": agent,
        "column": column,
        "card_events": card_events,
        "celery_status": celery_status,
        "worker_health": worker_health,
        "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
        "celery_soft_timeout_seconds": config.celery_soft_time_limit,
        "celery_hard_timeout_seconds": config.celery_time_limit,
    }


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    project_id: str | None = None,
    state: str | None = None,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    parsed_project_id = int(project_id) if project_id and project_id.isdigit() else None
    context = _build_jobs_list_context(
        uow=uow,
        dispatcher=dispatcher,
        project_id=parsed_project_id,
        state=state or None,
    )
    context["alert_message"] = alert_message
    context["alert_type"] = alert_type

    return templates.TemplateResponse(
        request=request,
        name="jobs/list.html",
        context=context,
    )


@router.get("/jobs/partials/content", response_class=HTMLResponse)
def list_jobs_partial(
    request: Request,
    project_id: str | None = None,
    state: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    parsed_project_id = int(project_id) if project_id and project_id.isdigit() else None
    context = _build_jobs_list_context(
        uow=uow,
        dispatcher=dispatcher,
        project_id=parsed_project_id,
        state=state or None,
    )
    return templates.TemplateResponse(
        request=request,
        name="jobs/_list_content.html",
        context=context,
    )


@router.get("/jobs/new", response_class=HTMLResponse)
def new_job_form(
    request: Request,
    project_id: int | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        projects = uow.projects.list_all(active_only=True)
        raw_columns = uow.columns.list_all(active_only=True)
        columns = []
        for c in raw_columns:
            agent = uow.agents.get_by_id(c.agent_id) if c.agent_id else None
            columns.append({"id": c.id, "column_name": c.column_name, "agent": agent})

        active_proj_id = project_id or (projects[0].id if projects else None)
        cards = uow.cards.list_by_project(active_proj_id) if active_proj_id else []

    return templates.TemplateResponse(
        request=request,
        name="jobs/form.html",
        context={
            "active_page": "jobs",
            "projects": projects,
            "columns": columns,
            "cards": cards,
        },
    )


@router.post("/jobs/new")
def create_job(
    project_id: int = Form(...),
    card_id: int = Form(...),
    flow_column_id: int = Form(...),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    with uow:
        col = uow.columns.get_by_id(flow_column_id)
        agent = uow.agents.get_by_id(col.agent_id) if col and col.agent_id else None

        job = uow.jobs.create(
            project_id=project_id,
            card_id=card_id,
            flow_column_id=flow_column_id,
            agent_id=agent.id if agent else None,
            cli_provider_snapshot=agent.cli_provider if agent else None,
            model_id_snapshot=agent.model_id if agent else None,
            target_column_snapshot=col.next_column_name if col else None,
            state="pending",
            process_status="Aguardando envio ao Celery",
        )
        uow.commit()
        job_id = job.id

    dispatched, _ = _dispatch_job_to_celery(job_id, uow, dispatcher)
    if dispatched:
        msg = quote_plus(f"Job #{job_id} criado e enviado para execução no Celery")
        return RedirectResponse(url=f"/jobs?alert_message={msg}", status_code=303)

    msg = quote_plus(f"Job #{job_id} criado, mas o broker Celery está indisponível no momento")
    return RedirectResponse(url=f"/jobs?alert_message={msg}&alert_type=error", status_code=303)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def get_job_detail(
    job_id: int,
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    context = _build_job_detail_context(job_id=job_id, uow=uow, dispatcher=dispatcher)
    if context is None:
        return RedirectResponse(url="/jobs?alert_message=Job+não+encontrado&alert_type=error", status_code=303)

    context["alert_message"] = alert_message
    context["alert_type"] = alert_type

    return templates.TemplateResponse(
        request=request,
        name="jobs/detail.html",
        context=context,
    )


@router.get("/jobs/{job_id}/partials/status", response_class=HTMLResponse)
def get_job_detail_partial(
    job_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    context = _build_job_detail_context(job_id=job_id, uow=uow, dispatcher=dispatcher)
    if context is None:
        return HTMLResponse("<p>Job não encontrado.</p>", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="jobs/_detail_content.html",
        context=context,
    )


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    task_id = None
    with uow:
        job = uow.jobs.get_by_id(job_id)
        if not job:
            return RedirectResponse(url="/jobs?alert_message=Job+não+encontrado&alert_type=error", status_code=303)
        task_id = job.celery_task_id
        uow.jobs.update(
            job_id,
            state="cancelled",
            process_status="Cancelado pelo usuário",
            finished_at=utc_now(),
        )
        uow.commit()

    if task_id:
        dispatcher.revoke_job(task_id)

    return RedirectResponse(url="/jobs?alert_message=Job+cancelado", status_code=303)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    with uow:
        job = uow.jobs.get_by_id(job_id)
        if not job:
            return RedirectResponse(url="/jobs?alert_message=Job+não+encontrado&alert_type=error", status_code=303)
        uow.jobs.update(
            job_id,
            state="pending",
            celery_task_id=None,
            process_status="Reenfileirando no Celery",
            error=None,
            output_summary=None,
            started_at=None,
            finished_at=None,
        )
        uow.commit()

    dispatched, _ = _dispatch_job_to_celery(job_id, uow, dispatcher)
    if dispatched:
        msg = quote_plus(f"Job #{job_id} reenfileirado no Celery")
        return RedirectResponse(url=f"/jobs/{job_id}?alert_message={msg}", status_code=303)

    msg = quote_plus(f"Job #{job_id} voltou para pendente, mas o broker Celery está indisponível")
    return RedirectResponse(url=f"/jobs/{job_id}?alert_message={msg}&alert_type=error", status_code=303)


@router.post("/jobs/{job_id}/delete")
def delete_job(
    job_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.jobs.delete(job_id)
        uow.commit()

    return RedirectResponse(url="/jobs?alert_message=Job+excluído", status_code=303)


@router.get("/runs", response_class=HTMLResponse)
def list_runs(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        raw_runs = uow.runs.list_recent(limit=50)
        projects = {p.id: p.name for p in uow.projects.list_all()}
        runs = []
        for r in raw_runs:
            runs.append({
                "id": r.id,
                "trigger": r.trigger,
                "project_name": projects.get(r.project_id) if r.project_id else "Todos",
                "project_provider_used": r.project_provider_used,
                "cards_synced": r.cards_synced,
                "jobs_created": r.jobs_created,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            })

    return templates.TemplateResponse(
        request=request,
        name="runs/list.html",
        context={
            "active_page": "runs",
            "runs": runs,
        },
    )


@router.get("/cards/{card_id}", response_class=HTMLResponse)
def card_details(
    card_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        card = uow.cards.get_by_id(card_id)
        if not card:
            return RedirectResponse(url="/projects?alert_message=Card+não+encontrado&alert_type=error", status_code=303)
        project = uow.projects.get_by_id(card.project_id)
        events = uow.events.list_by_card(card_id)

    mock_job = type(
        "MockJob",
        (),
        {
            "id": "N/A",
            "state": "N/A",
            "cli_provider_snapshot": "—",
            "model_id_snapshot": "—",
            "target_column_snapshot": "—",
            "celery_task_id": None,
            "process_status": None,
            "created_at": card.first_seen_at,
            "started_at": None,
            "finished_at": None,
            "output_summary": None,
            "error": None,
        },
    )()

    return templates.TemplateResponse(
        request=request,
        name="jobs/detail.html",
        context={
            "active_page": "projects",
            "job": mock_job,
            "project": project,
            "card": card,
            "agent": None,
            "column": None,
            "card_events": events,
            "celery_status": None,
            "worker_health": None,
            "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
            "celery_soft_timeout_seconds": config.celery_soft_time_limit,
            "celery_hard_timeout_seconds": config.celery_time_limit,
        },
    )
