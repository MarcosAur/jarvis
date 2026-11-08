from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.web.dependencies import get_uow

router = APIRouter(prefix="/columns", tags=["columns"])
templates = Jinja2Templates(directory="src/pipeline/web/templates")


@router.get("", response_class=HTMLResponse)
def list_columns(
    request: Request,
    alert_message: str | None = None,
    alert_type: str | None = None,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        raw_cols = uow.columns.list_all()
        columns = []
        for c in raw_cols:
            agent = uow.agents.get_by_id(c.agent_id) if c.agent_id else None
            columns.append({
                "id": c.id,
                "order_index": c.order_index,
                "column_name": c.column_name,
                "identifier": c.identifier,
                "agent": agent,
                "next_column_name": c.next_column_name,
                "active": c.active,
            })

    return templates.TemplateResponse(
        request=request,
        name="columns/list.html",
        context={
            "active_page": "columns",
            "columns": columns,
            "alert_message": alert_message,
            "alert_type": alert_type,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_column_form(
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        agents = uow.agents.list_all(active_only=True)

    return templates.TemplateResponse(
        request=request,
        name="columns/form.html",
        context={
            "active_page": "columns",
            "column": None,
            "agents": agents,
        },
    )


@router.post("/new")
def create_column(
    column_name: str = Form(...),
    identifier: str = Form(...),
    agent_id: str | None = Form(None),
    next_column_name: str | None = Form(None),
    order_index: int = Form(1),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    actual_agent_id = int(agent_id) if agent_id and agent_id.strip() else None
    actual_next = next_column_name.strip() if next_column_name and next_column_name.strip() else None

    with uow:
        uow.columns.create(
            identifier=identifier.strip(),
            column_name=column_name.strip(),
            agent_id=actual_agent_id,
            next_column_name=actual_next,
            order_index=order_index,
            active=active,
        )
        uow.commit()

    return RedirectResponse(url="/columns?alert_message=Coluna+criada+com+sucesso", status_code=303)


@router.get("/{column_id}/edit", response_class=HTMLResponse)
def edit_column_form(
    column_id: int,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        col = uow.columns.get_by_id(column_id)
        if not col:
            return RedirectResponse(url="/columns?alert_message=Coluna+não+encontrada&alert_type=error", status_code=303)
        agents = uow.agents.list_all(active_only=True)

    return templates.TemplateResponse(
        request=request,
        name="columns/form.html",
        context={
            "active_page": "columns",
            "column": col,
            "agents": agents,
        },
    )


@router.post("/{column_id}/edit")
def update_column(
    column_id: int,
    column_name: str = Form(...),
    identifier: str = Form(...),
    agent_id: str | None = Form(None),
    next_column_name: str | None = Form(None),
    order_index: int = Form(1),
    active: bool = Form(False),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    actual_agent_id = int(agent_id) if agent_id and agent_id.strip() else None
    actual_next = next_column_name.strip() if next_column_name and next_column_name.strip() else None

    with uow:
        uow.columns.update(
            column_id,
            column_name=column_name.strip(),
            identifier=identifier.strip(),
            agent_id=actual_agent_id,
            next_column_name=actual_next,
            order_index=order_index,
            active=active,
        )
        uow.commit()

    return RedirectResponse(url="/columns?alert_message=Coluna+atualizada+com+sucesso", status_code=303)


@router.post("/{column_id}/toggle")
def toggle_column(
    column_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        col = uow.columns.get_by_id(column_id)
        if col:
            uow.columns.update(column_id, active=not col.active)
            uow.commit()

    return RedirectResponse(url="/columns", status_code=303)


@router.post("/{column_id}/delete")
def delete_column(
    column_id: int,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
):
    with uow:
        uow.columns.delete(column_id)
        uow.commit()

    return RedirectResponse(url="/columns?alert_message=Coluna+excluída+com+sucesso", status_code=303)
