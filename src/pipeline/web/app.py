from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pipeline.adapters.db.seed import seed_database
from pipeline.config import config
from pipeline.web.dependencies import get_model_catalog_service
from pipeline.web.routes import (
    agents_router,
    columns_router,
    jobs_router,
    projects_router,
    settings_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure db tables and initial seed data exist
    seed_database()
    # Cache models of installed CLIs
    try:
        catalog = get_model_catalog_service()
        catalog.sync_all_installed_providers()
    except Exception:
        pass
    yield


app = FastAPI(
    title="Pipeline de Desenvolvimento Automático com IA",
    description="Orquestrador Open Source de desenvolvimento automático baseado em SOLID e CLIs locais.",
    version="0.1.0",
    lifespan=lifespan,
    debug=config.DEBUG,
)

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers (CRUDs 1 a 5)
app.include_router(agents_router)
app.include_router(projects_router)
app.include_router(columns_router)
app.include_router(settings_router)
app.include_router(jobs_router)


@app.get("/", include_in_schema=False)
def index_redirect():
    return RedirectResponse(url="/projects")
