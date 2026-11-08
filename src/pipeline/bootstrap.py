from pipeline.adapters.cli_providers import (
    AgyCliProvider,
    ClaudeCliProvider,
    CodexCliProvider,
    GeminiCliProvider,
)
from pipeline.adapters.project_providers import (
    GitHubProjectProvider,
    JiraProjectProvider,
    TrelloProjectProvider,
)
from pipeline.domain.ports.cli_provider import CliModelProvider
from pipeline.domain.ports.project_provider import ProjectProvider
from pipeline.domain.registry import Registry

# Global registries for pluggable providers (SOLID OCP)
cli_registry: Registry[CliModelProvider] = Registry[CliModelProvider]("CliModelProviders")
project_registry: Registry[ProjectProvider] = Registry[ProjectProvider]("ProjectProviders")


def register_defaults() -> None:
    # 1. Register CLI Model Providers
    cli_registry.register(AgyCliProvider())
    cli_registry.register(GeminiCliProvider())
    cli_registry.register(ClaudeCliProvider())
    cli_registry.register(CodexCliProvider())

    # 2. Register Project Board Providers
    project_registry.register(GitHubProjectProvider())
    project_registry.register(JiraProjectProvider())
    project_registry.register(TrelloProjectProvider())


# Automatically register default providers on import
register_defaults()
