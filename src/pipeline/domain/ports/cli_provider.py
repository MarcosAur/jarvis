from typing import ClassVar, Protocol, runtime_checkable
from pipeline.domain.entities import CliPromptRequest, CliPromptResult, ModelOption


@runtime_checkable
class CliModelProvider(Protocol):
    """Port for AI CLI model providers (e.g., agy, gemini, claude, codex)."""

    provider_key: ClassVar[str]
    display_name: ClassVar[str]
    binary_name: ClassVar[str]

    def is_installed(self) -> bool:
        """Checks if the CLI binary exists in the system PATH."""
        ...

    def list_models(self) -> list[ModelOption]:
        """Lists available models from this CLI."""
        ...

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        """Executes a prompt through the CLI binary."""
        ...
