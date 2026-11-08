from collections.abc import Callable
from sqlmodel import Session
from pipeline.adapters.db.engine import get_engine
from pipeline.adapters.db.repositories import (
    SqlAgentRepository,
    SqlCardEventRepository,
    SqlCardRepository,
    SqlCliModelRepository,
    SqlFlowColumnRepository,
    SqlJobRepository,
    SqlPipelineRunRepository,
    SqlProjectRepository,
    SqlSettingsRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or (lambda: Session(get_engine(), expire_on_commit=False))
        self.session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.settings = SqlSettingsRepository(self.session)
        self.agents = SqlAgentRepository(self.session)
        self.projects = SqlProjectRepository(self.session)
        self.columns = SqlFlowColumnRepository(self.session)
        self.jobs = SqlJobRepository(self.session)
        self.cards = SqlCardRepository(self.session)
        self.events = SqlCardEventRepository(self.session)
        self.models = SqlCliModelRepository(self.session)
        self.runs = SqlPipelineRunRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session is not None:
            if exc_type is not None:
                self.rollback()
            self.session.close()

    def commit(self) -> None:
        if self.session is not None:
            self.session.commit()

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
