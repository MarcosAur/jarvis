import logging
from pipeline.bootstrap import cli_registry
from pipeline.domain.entities import ModelOption
from pipeline.domain.ports.uow import UnitOfWork

logger = logging.getLogger(__name__)


class ModelCatalogService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    def sync_models_for_provider(self, provider_key: str) -> list[ModelOption]:
        provider = cli_registry.get_or_none(provider_key)
        if not provider:
            return []

        models = provider.list_models()
        with self.uow_factory() as uow:
            uow.models.upsert_models(provider_key, models)
            uow.commit()

        return models

    def sync_all_installed_providers(self) -> dict[str, int]:
        results: dict[str, int] = {}
        with self.uow_factory() as uow:
            for provider in cli_registry.list_all():
                if provider.is_installed():
                    try:
                        models = provider.list_models()
                        uow.models.upsert_models(provider.provider_key, models)
                        results[provider.provider_key] = len(models)
                    except Exception as e:
                        logger.warning("Falha ao sincronizar modelos de %s: %s", provider.provider_key, e)
                        results[provider.provider_key] = 0
                else:
                    results[provider.provider_key] = 0
            uow.commit()
        return results
