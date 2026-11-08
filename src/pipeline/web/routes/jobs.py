from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.job_runner_service import JobRunnerService
from pipeline.web.dependencies import get_job_runner_service, get_uow

router = APIRouter(tags=["jobs"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    project_id: int | None = None,
    state: str | None = None,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
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
                "created_at": j.created_at,
            })

    return templates.TemplateResponse(
        request=request,
        name="jobs/list.html",
        context={
            "active_page": "jobs",
            "jobs": jobs,
            "projects": projects,
            "selected_project_id": project_id,
            "selected_state": state,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
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

        # Get cards for first project if available
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
):
    with uow:
        col = uow.columns.get_by_id(flow_column_id)
        agent = uow.agents.get_by_id(col.agent_id) if col and col.agent_id else None

        uow.jobs.create(
            project_id=project_id,
            card_id=card_id,
            flow_column_id=flow_column_id,
            agent_id=agent.id if agent else None,
            cli_provider_snapshot=agent.cli_provider if agent else None,
            model_id_snapshot=agent.model_id if agent else None,
            target_column_snapshot=col.next_column_name if col else None,
            state="pending",
        )
        uow.commit()

    return RedirectResponse(url="/jobs?alert_message=Job+enfileirado+com+sucesso", status_code=303)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def get_job_detail(
    job_id: int,
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        job = uow.jobs.get_by_id(job_id)
        if not job:
            return RedirectResponse(url="/jobs?alert_message=Job+não+encontrado&alert_type=error", status_code=303)

        project = uow.projects.get_by_id(job.project_id)
        card = uow.cards.get_by_id(job.card_id)
        agent = uow.agents.get_by_id(job.agent_id) if job.agent_id else None
        column = uow.columns.get_by_id(job.flow_column_id)
        card_events = uow.events.list_by_card(job.card_id) if job.card_id else []

    return templates.TemplateResponse(
        request=request,
        name="jobs/detail.html",
        context={
            "active_page": "jobs",
            "job": job,
            "project": project,
            "card": card,
            "agent": agent,
            "column": column,
            "card_events": card_events,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.jobs.update(job_id, state="cancelled")
        uow.commit()

    return RedirectResponse(url="/jobs?alert_message=Job+cancelado", status_code=303)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.jobs.update(job_id, state="pending", error=None, output_summary=None)
        uow.commit()

    return RedirectResponse(url="/jobs?alert_message=Job+reenfileirado", status_code=303)


@router.post("/jobs/{job_id}/run")
def execute_job(
    job_id: int,
    mode: str = Form("live"),
    runner: JobRunnerService = Depends(get_job_runner_service),
):
    dry_run = (mode == "dry_run")
    res = runner.run_job(job_id, dry_run=dry_run)
    if res.get("success"):
        label = "em+modo+simulação+(Dry-run)" if dry_run else "com+sucesso+pela+IA!"
        return RedirectResponse(url=f"/jobs/{job_id}?alert_message=Job+executado+{label}", status_code=303)
    else:
        return RedirectResponse(url=f"/jobs/{job_id}?alert_message=Falha+na+execução:+{res.get('error')}&alert_type=error", status_code=303)


@router.post("/jobs/run-all")
def execute_all_pending_jobs(
    mode: str = Form("live"),
    runner: JobRunnerService = Depends(get_job_runner_service),
):
    dry_run = (mode == "dry_run")
    results = runner.run_all_pending(dry_run=dry_run)
    successes = sum(1 for r in results if r.get("success"))
    mode_label = "em+modo+simulação+(dry-run)" if dry_run else "com+IA+real"
    return RedirectResponse(
        url=f"/jobs?alert_message=Processados+{len(results)}+job(s)+{mode_label}+(Sucessos:+{successes})",
        status_code=303,
    )


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

    return templates.TemplateResponse(
        request=request,
        name="jobs/detail.html",
        context={
            "active_page": "projects",
            "job": type("MockJob", (), {"id": "N/A", "state": "N/A", "cli_provider_snapshot": "—", "model_id_snapshot": "—", "target_column_snapshot": "—", "created_at": card.first_seen_at, "started_at": None, "finished_at": None, "output_summary": None, "error": None})(),
            "project": project,
            "card": card,
            "agent": None,
            "column": None,
            "card_events": events,
        },
    )
