from sqlalchemy import event, text
from sqlmodel import SQLModel, create_engine
from pipeline.config import config

_engine = None


def get_engine(db_url: str | None = None):
    global _engine
    if _engine is not None and db_url is None:
        return _engine

    url = db_url or config.DATABASE_URL
    # Ensure data dir exists if sqlite file path
    if url.startswith("sqlite:///"):
        config.setup_dirs()

    engine = create_engine(
        url,
        echo=config.DEBUG,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    if db_url is None:
        _engine = engine
    return engine


def _ensure_sqlite_job_columns(engine) -> None:
    """Safely add new Job tracking columns to pre-existing SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
        if not rows:
            return
        existing_cols = {row[1] for row in rows}
        if "celery_task_id" not in existing_cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN celery_task_id VARCHAR"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_celery_task_id ON jobs (celery_task_id)"))
        if "process_status" not in existing_cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN process_status VARCHAR"))


def _ensure_sqlite_agent_columns(engine) -> None:
    """Safely add new Agent concurrency columns to pre-existing SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(agents)")).fetchall()
        if not rows:
            return
        existing_cols = {row[1] for row in rows}
        if "max_parallel_executions" not in existing_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN max_parallel_executions INTEGER NOT NULL DEFAULT 1"))


def _ensure_sqlite_project_columns(engine) -> None:
    """Safely add Project.project_provider to pre-existing SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(projects)")).fetchall()
        if not rows:
            return
        existing_cols = {row[1] for row in rows}
        if "project_provider" not in existing_cols:
            conn.execute(text("ALTER TABLE projects ADD COLUMN project_provider VARCHAR NOT NULL DEFAULT 'github'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_project_provider ON projects (project_provider)"))
            # Preserve legacy active_project_provider on existing projects if app_settings exists
            app_rows = conn.execute(text("PRAGMA table_info(app_settings)")).fetchall()
            if app_rows:
                row = conn.execute(text("SELECT active_project_provider FROM app_settings WHERE id = 1")).first()
                if row and row[0]:
                    conn.execute(
                        text("UPDATE projects SET project_provider = :prov"),
                        {"prov": str(row[0]).strip()},
                    )


def init_db(engine=None) -> None:
    eng = engine or get_engine()
    SQLModel.metadata.create_all(eng)
    _ensure_sqlite_job_columns(eng)
    _ensure_sqlite_agent_columns(eng)
    _ensure_sqlite_project_columns(eng)


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
