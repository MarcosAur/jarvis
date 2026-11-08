from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.application.job_runner_service import JobRunnerService
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.application.sync_service import SyncService


def get_uow() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork()


def get_sync_service() -> SyncService:
    return SyncService()


def get_model_catalog_service() -> ModelCatalogService:
    return ModelCatalogService(SqlAlchemyUnitOfWork)


def get_job_runner_service() -> JobRunnerService:
    return JobRunnerService(SqlAlchemyUnitOfWork)


def get_orchestrator() -> PipelineOrchestrator:
    return PipelineOrchestrator(SqlAlchemyUnitOfWork, get_sync_service())
