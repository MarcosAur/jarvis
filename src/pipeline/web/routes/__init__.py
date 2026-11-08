from pipeline.web.routes.agents import router as agents_router
from pipeline.web.routes.columns import router as columns_router
from pipeline.web.routes.jobs import router as jobs_router
from pipeline.web.routes.projects import router as projects_router
from pipeline.web.routes.settings import router as settings_router

__all__ = [
    "agents_router",
    "projects_router",
    "columns_router",
    "settings_router",
    "jobs_router",
]
