import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.orm_models import utc_now
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.config import config
from pipeline.domain.ports.job_dispatcher import CeleryTaskStatus, JobDispatcher
from pipeline.web.dependencies import get_job_dispatcher, get_uow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


def _format_duration(started_at, finished_at, fallback_now=None) -> str:
    if not started_at:
        return "—"
    end = finished_at or fallback_now or utc_now()
    if started_at.tzinfo is None and end.tzinfo is not None:
        started_at = started_at.replace(tzinfo=end.tzinfo)
    seconds = max(int((end - started_at).total_seconds()), 0)
    if seconds >= 60:
        mins, secs = divmod(seconds, 60)
        return f"{mins}m {secs:02d}s"
    return f"{seconds}s"


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


def _build_job_detail_context(
    job_id: int,
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
    worker_health=None,
) -> dict | None:
    health = worker_health or dispatcher.get_worker_health()
    now_utc = utc_now()

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
        if health.broker_available:
            celery_status = dispatcher.get_task_status(job.celery_task_id)
        else:
            celery_status = CeleryTaskStatus(
                task_id=job.celery_task_id,
                state="BROKER_OFFLINE",
                detail=health.error,
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
        "worker_health": health,
        "duration_label": _format_duration(job.started_at, job.finished_at, now_utc),
        "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
        "celery_soft_timeout_seconds": config.celery_soft_time_limit,
        "celery_hard_timeout_seconds": config.celery_time_limit,
    }


def _build_jobs_list_context(
    uow: SqlAlchemyUnitOfWork,
    dispatcher: JobDispatcher,
    project_id: int | None = None,
    state: str | None = None,
    selected_job_id: int | None = None,
) -> dict:
    worker_health = dispatcher.get_worker_health()
    now_utc = utc_now()

    with uow:
        projects = uow.projects.list_all()
        proj_map = {p.id: p for p in projects}
        agents = uow.agents.list_all()
        agent_map = {a.id: a for a in agents}
        columns = uow.columns.list_all()
        col_map = {c.id: c for c in columns}
        settings = uow.settings.get()

        # Stats for the project filter (across all states)
        all_project_jobs = uow.jobs.list_all(project_id=project_id, limit=500)
        state_counts = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
        durations_sec: list[int] = []
        for pj in all_project_jobs:
            if pj.state in state_counts:
                state_counts[pj.state] += 1
            if pj.started_at and pj.finished_at:
                s_at = pj.started_at
                f_at = pj.finished_at
                if s_at.tzinfo is None and f_at.tzinfo is not None:
                    s_at = s_at.replace(tzinfo=f_at.tzinfo)
                durations_sec.append(max(int((f_at - s_at).total_seconds()), 0))

        finished_total = state_counts["succeeded"] + state_counts["failed"]
        success_rate = round((state_counts["succeeded"] / finished_total) * 100, 1) if finished_total > 0 else 100.0 if state_counts["succeeded"] > 0 else 0.0
        if durations_sec:
            avg_sec = int(sum(durations_sec) / len(durations_sec))
            avg_duration = f"{avg_sec // 60}m {avg_sec % 60:02d}s" if avg_sec >= 60 else f"{avg_sec}s"
        else:
            avg_duration = "—"

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
                "project_id": j.project_id,
                "project_name": proj.name if proj else f"Projeto #{j.project_id}",
                "card_title": card.title if card else f"Card #{j.card_id}",
                "card_issue": card.issue_number if card else None,
                "card_id": j.card_id,
                "card_rework_count": card.rework_count if card else 0,
                "column_name": col.column_name if col else "Desconhecida",
                "target_column_snapshot": j.target_column_snapshot,
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
                "duration_label": _format_duration(j.started_at, j.finished_at, now_utc),
            })

    # Determine selected job for the master-detail inspector
    effective_selected_id = selected_job_id
    if effective_selected_id is None and jobs:
        effective_selected_id = jobs[0]["id"]

    selected_detail = None
    if effective_selected_id is not None:
        selected_detail = _build_job_detail_context(
            job_id=effective_selected_id,
            uow=uow,
            dispatcher=dispatcher,
            worker_health=worker_health,
        )

    selected_project = next((p for p in projects if p.id == project_id), None)

    return {
        "active_page": "jobs",
        "jobs": jobs,
        "projects": projects,
        "selected_project": selected_project,
        "selected_project_id": project_id,
        "selected_state": state,
        "selected_job_id": effective_selected_id,
        "selected_detail": selected_detail,
        "default_cli_provider": settings.default_cli_provider,
        "stats": {
            "total": len(all_project_jobs),
            "pending": state_counts["pending"],
            "running": state_counts["running"],
            "succeeded": state_counts["succeeded"],
            "failed": state_counts["failed"],
            "cancelled": state_counts["cancelled"],
            "success_rate": success_rate,
            "avg_duration": avg_duration,
        },
        "worker_health": worker_health,
        "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
        "celery_soft_timeout_seconds": config.celery_soft_time_limit,
        "celery_hard_timeout_seconds": config.celery_time_limit,
        "pipeline_interval_seconds": config.CELERY_PIPELINE_INTERVAL_SECONDS,
    }


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    project_id: str | None = None,
    state: str | None = None,
    selected_job_id: str | None = None,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    parsed_project_id = int(project_id) if project_id and project_id.isdigit() else None
    parsed_selected_job_id = int(selected_job_id) if selected_job_id and selected_job_id.isdigit() else None
    context = _build_jobs_list_context(
        uow=uow,
        dispatcher=dispatcher,
        project_id=parsed_project_id,
        state=state or None,
        selected_job_id=parsed_selected_job_id,
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
    selected_job_id: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    parsed_project_id = int(project_id) if project_id and project_id.isdigit() else None
    parsed_selected_job_id = int(selected_job_id) if selected_job_id and selected_job_id.isdigit() else None
    context = _build_jobs_list_context(
        uow=uow,
        dispatcher=dispatcher,
        project_id=parsed_project_id,
        state=state or None,
        selected_job_id=parsed_selected_job_id,
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
    card_id: int | None = None,
    flow_column_id: int | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
):
    worker_health = dispatcher.get_worker_health()
    with uow:
        projects = uow.projects.list_all(active_only=True)
        raw_columns = uow.columns.list_all(active_only=True)
        columns = []
        for c in raw_columns:
            agent = uow.agents.get_by_id(c.agent_id) if c.agent_id else None
            columns.append(
                {
                    "id": c.id,
                    "column_name": c.column_name,
                    "next_column_name": c.next_column_name,
                    "identifier": c.identifier,
                    "order_index": c.order_index,
                    "agent": agent,
                }
            )

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
            "selected_project_id": active_proj_id,
            "selected_card_id": card_id,
            "selected_column_id": flow_column_id,
            "worker_health": worker_health,
            "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
            "celery_soft_timeout_seconds": config.celery_soft_time_limit,
            "celery_hard_timeout_seconds": config.celery_time_limit,
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
        return RedirectResponse(url=f"/jobs?selected_job_id={job_id}&alert_message={msg}", status_code=303)

    msg = quote_plus(f"Job #{job_id} criado, mas o broker Celery está indisponível no momento")
    return RedirectResponse(url=f"/jobs?selected_job_id={job_id}&alert_message={msg}&alert_type=error", status_code=303)


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
        return HTMLResponse("<p class='p-4 text-error'>Job não encontrado.</p>", status_code=404)

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

    return RedirectResponse(url=f"/jobs?selected_job_id={job_id}&alert_message=Job+cancelado", status_code=303)


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


_RUN_RANGE_DAYS = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
}

_JOB_STATUS_LABELS = {
    "done": "Sucesso",
    "running": "Executando",
    "pending": "Na fila",
    "failed": "Falhou",
    "cancelled": "Cancelado",
}


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_avg_duration(seconds_list: list[float]) -> str:
    if not seconds_list:
        return "—"
    avg = max(int(sum(seconds_list) / len(seconds_list)), 0)
    if avg >= 60:
        mins, secs = divmod(avg, 60)
        return f"{mins}m {secs:02d}s"
    return f"{avg}s"


def _build_job_audit_item(
    job: Any,
    projects: dict[int, Any],
    agents: dict[int, Any],
    columns: dict[int, Any],
    uow: SqlAlchemyUnitOfWork,
    card_cache: dict[int, Any],
    events_cache: dict[int, list[Any]],
) -> dict[str, Any]:
    if job.card_id not in card_cache:
        card_cache[job.card_id] = uow.cards.get_by_id(job.card_id)
    card = card_cache[job.card_id]

    if job.card_id not in events_cache:
        events_cache[job.card_id] = uow.events.list_by_card(job.card_id)
    card_events = events_cache[job.card_id]

    project = projects.get(job.project_id)
    agent = agents.get(job.agent_id) if job.agent_id else None
    col = columns.get(job.flow_column_id)

    rework_events = sum(1 for ev in card_events if ev.is_rework)
    timeline: list[dict[str, str]] = []
    if job.created_at:
        timeline.append({
            "time": job.created_at.strftime("%H:%M:%S"),
            "label": f"Job #{job.id} enfileirado ({col.column_name if col else 'Etapa'})",
            "tone": "muted",
        })
    if job.started_at:
        timeline.append({
            "time": job.started_at.strftime("%H:%M:%S"),
            "label": f"Agente {agent.name if agent else 'IA'} iniciado via {job.cli_provider_snapshot or 'CLI'}",
            "tone": "secondary",
        })
    for ev in card_events[:4]:
        timeline.append({
            "time": ev.created_at.strftime("%H:%M:%S") if ev.created_at else "—",
            "label": f"{ev.event_type}: {ev.from_column or '—'} → {ev.to_column or '—'}" + (" (Retrabalho)" if ev.is_rework else ""),
            "tone": "warning" if ev.is_rework else "muted",
        })
    if job.finished_at:
        timeline.append({
            "time": job.finished_at.strftime("%H:%M:%S"),
            "label": (
                f"Concluído → {job.target_column_snapshot or 'Etapa final'}"
                if job.state == "done"
                else f"Finalizado com status: {_JOB_STATUS_LABELS.get(job.state, job.state)}"
            ),
            "tone": "tertiary" if job.state == "done" else "error",
        })

    dur_seconds: float | None = None
    start_u = _to_utc(job.started_at)
    end_u = _to_utc(job.finished_at)
    if start_u and end_u:
        dur_seconds = max((end_u - start_u).total_seconds(), 0.0)

    return {
        "id": job.id,
        "project_id": job.project_id,
        "project_name": project.name if project else f"Projeto #{job.project_id}",
        "card_id": job.card_id,
        "card_title": card.title if card else f"Card #{job.card_id}",
        "card_issue_number": card.issue_number if card else None,
        "card_url": card.url if card else None,
        "card_rework_count": card.rework_count if card else 0,
        "rework_events_count": rework_events,
        "agent_id": job.agent_id,
        "agent_name": agent.name if agent else "Agente Removido",
        "cli_provider": job.cli_provider_snapshot or (agent.cli_provider if agent else "—"),
        "model_id": job.model_id_snapshot or (agent.model_id if agent else "—"),
        "origin_column": col.column_name if col else "—",
        "target_column": job.target_column_snapshot or (col.next_column_name if col and col.next_column_name else "Fim do Fluxo"),
        "iteration": job.iteration,
        "state": job.state,
        "state_label": _JOB_STATUS_LABELS.get(job.state, job.state),
        "process_status": job.process_status,
        "output_summary": job.output_summary,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "duration": _format_duration(job.started_at, job.finished_at),
        "duration_seconds": dur_seconds,
        "timeline": timeline,
    }


def _collect_audit_data(
    uow: SqlAlchemyUnitOfWork,
    range_filter: str = "all",
    project_id: int | None = None,
    agent_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    selected_job_id: int | None = None,
) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    days = _RUN_RANGE_DAYS.get(range_filter)
    cutoff = now_utc - timedelta(days=days) if days is not None else None

    all_projects = uow.projects.list_all()
    all_agents = uow.agents.list_all()
    all_columns = uow.columns.list_all()
    projects_map = {p.id: p for p in all_projects if p.id is not None}
    agents_map = {a.id: a for a in all_agents if a.id is not None}
    columns_map = {c.id: c for c in all_columns if c.id is not None}

    raw_runs = uow.runs.list_recent(limit=200)
    raw_jobs = uow.jobs.list_all(limit=300)

    filtered_runs: list[dict[str, Any]] = []
    for r in raw_runs:
        started_u = _to_utc(r.started_at)
        if cutoff and started_u and started_u < cutoff:
            continue
        if project_id is not None and r.project_id != project_id:
            continue
        proj_name = projects_map[r.project_id].name if (r.project_id and r.project_id in projects_map) else "Todos os Projetos"
        if q:
            ql = q.strip().lower()
            hay = f"#{r.id} {r.trigger} {proj_name} {r.project_provider_used} {r.status}".lower()
            if ql not in hay:
                continue
        filtered_runs.append({
            "id": r.id,
            "trigger": r.trigger,
            "project_id": r.project_id,
            "project_name": proj_name,
            "project_provider_used": r.project_provider_used,
            "cards_synced": r.cards_synced,
            "jobs_created": r.jobs_created,
            "status": r.status,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "duration": _format_duration(r.started_at, r.finished_at),
        })

    card_cache: dict[int, Any] = {}
    events_cache: dict[int, list[Any]] = {}
    all_job_items: list[dict[str, Any]] = []

    for job in raw_jobs:
        created_u = _to_utc(job.created_at)
        if cutoff and created_u and created_u < cutoff:
            continue
        if project_id is not None and job.project_id != project_id:
            continue
        if agent_id is not None and job.agent_id != agent_id:
            continue
        if status and status != "all" and job.state != status:
            continue

        item = _build_job_audit_item(job, projects_map, agents_map, columns_map, uow, card_cache, events_cache)
        if q:
            ql = q.strip().lower()
            hay = (
                f"#{item['id']} #{item['card_issue_number'] or item['card_id']} "
                f"{item['card_title']} {item['project_name']} {item['agent_name']} "
                f"{item['model_id']} {item['origin_column']} {item['target_column']}"
            ).lower()
            if ql not in hay:
                continue
        all_job_items.append(item)

    finished_jobs = [j for j in all_job_items if j["state"] in ("done", "failed")]
    done_jobs_count = sum(1 for j in all_job_items if j["state"] == "done")
    success_rate = round((done_jobs_count / len(finished_jobs)) * 100, 1) if finished_jobs else None
    total_reworks = sum(j["rework_events_count"] for j in all_job_items)
    durations = [j["duration_seconds"] for j in finished_jobs if j["duration_seconds"] is not None]
    avg_duration = _format_avg_duration(durations)

    inspected_job = None
    if selected_job_id is not None:
        inspected_job = next((j for j in all_job_items if j["id"] == selected_job_id), None)
    if inspected_job is None and all_job_items:
        inspected_job = all_job_items[0]

    return {
        "active_page": "runs",
        "runs": filtered_runs,
        "job_items": all_job_items,
        "total_jobs_raw": len(raw_jobs),
        "inspected_job": inspected_job,
        "projects": all_projects,
        "agents": all_agents,
        "range_filter": range_filter,
        "selected_project_id": project_id,
        "selected_agent_id": agent_id,
        "selected_status": status or "all",
        "search_query": q or "",
        "done_jobs_count": done_jobs_count,
        "finished_jobs_count": len(finished_jobs),
        "success_rate": success_rate,
        "total_reworks": total_reworks,
        "avg_duration": avg_duration,
        "total_cards_synced": sum(r["cards_synced"] for r in filtered_runs),
        "ok_runs_count": sum(1 for r in filtered_runs if r["status"] == "ok"),
    }


@router.get("/runs", response_class=HTMLResponse)
def list_runs(
    request: Request,
    range: str = "all",
    project_id: str | None = None,
    agent_id: str | None = None,
    status: str = "all",
    q: str | None = None,
    selected_job_id: int | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    parsed_project_id = int(project_id) if project_id and project_id.strip().isdigit() else None
    parsed_agent_id = int(agent_id) if agent_id and agent_id.strip().isdigit() else None

    with uow:
        context = _collect_audit_data(
            uow,
            range_filter=range,
            project_id=parsed_project_id,
            agent_id=parsed_agent_id,
            status=status,
            q=q,
            selected_job_id=selected_job_id,
        )

    return templates.TemplateResponse(
        request=request,
        name="runs/list.html",
        context=context,
    )


@router.get("/runs/inspector/{job_id}", response_class=HTMLResponse)
def audit_inspector_partial(
    job_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        job = uow.jobs.get_by_id(job_id)
        inspected_job = None
        if job:
            projects_map = {p.id: p for p in uow.projects.list_all() if p.id is not None}
            agents_map = {a.id: a for a in uow.agents.list_all() if a.id is not None}
            columns_map = {c.id: c for c in uow.columns.list_all() if c.id is not None}
            inspected_job = _build_job_audit_item(job, projects_map, agents_map, columns_map, uow, {}, {})

    return templates.TemplateResponse(
        request=request,
        name="runs/_inspector.html",
        context={"inspected_job": inspected_job},
    )


@router.get("/runs/export")
def export_runs_audit(
    format: str = "json",
    range: str = "all",
    project_id: str | None = None,
    agent_id: str | None = None,
    status: str = "all",
    q: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    parsed_project_id = int(project_id) if project_id and project_id.strip().isdigit() else None
    parsed_agent_id = int(agent_id) if agent_id and agent_id.strip().isdigit() else None

    with uow:
        data = _collect_audit_data(
            uow,
            range_filter=range,
            project_id=parsed_project_id,
            agent_id=parsed_agent_id,
            status=status,
            q=q,
        )

    export_rows = [
        {
            "job_id": j["id"],
            "project": j["project_name"],
            "card_id": j["card_issue_number"] or j["card_id"],
            "card_title": j["card_title"],
            "agent": j["agent_name"],
            "cli_provider": j["cli_provider"],
            "model_id": j["model_id"],
            "origin_column": j["origin_column"],
            "target_column": j["target_column"],
            "reworks": j["rework_events_count"],
            "state": j["state"],
            "duration": j["duration"],
            "created_at": j["created_at"].isoformat() if j["created_at"] else None,
            "finished_at": j["finished_at"].isoformat() if j["finished_at"] else None,
        }
        for j in data["job_items"]
    ]

    if format.lower() == "csv":
        buf = io.StringIO()
        fieldnames = list(export_rows[0].keys()) if export_rows else [
            "job_id", "project", "card_id", "card_title", "agent", "cli_provider",
            "model_id", "origin_column", "target_column", "reworks", "state", "duration",
            "created_at", "finished_at",
        ]
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(export_rows)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="ai-pipeline-audit.csv"'},
        )

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "range": range,
        "jobs": export_rows,
        "pipeline_runs": [
            {
                "run_id": r["id"],
                "trigger": r["trigger"],
                "project": r["project_name"],
                "provider": r["project_provider_used"],
                "cards_synced": r["cards_synced"],
                "jobs_created": r["jobs_created"],
                "status": r["status"],
                "duration": r["duration"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            }
            for r in data["runs"]
        ],
    }
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-pipeline-audit.json"'},
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
            "duration_label": "—",
            "agent_timeout_seconds": config.CLI_TIMEOUT_SECONDS,
            "celery_soft_timeout_seconds": config.celery_soft_time_limit,
            "celery_hard_timeout_seconds": config.celery_time_limit,
        },
    )
