from sqlalchemy import event
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


def init_db(engine=None) -> None:
    eng = engine or get_engine()
    SQLModel.metadata.create_all(eng)
