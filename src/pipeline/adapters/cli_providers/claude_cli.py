from pipeline.adapters.cli_providers.base import BaseSubprocessCliProvider
from pipeline.domain.entities import CliPromptRequest, CliPromptResult, ModelOption

DEFAULT_CLAUDE_MODELS = [
    ModelOption(id="claude-3-7-sonnet-latest", label="Claude 3.7 Sonnet", family="claude", cli_provider="claude"),
    ModelOption(id="claude-3-5-sonnet-latest", label="Claude 3.5 Sonnet", family="claude", cli_provider="claude"),
    ModelOption(id="claude-3-5-haiku-latest", label="Claude 3.5 Haiku", family="claude", cli_provider="claude"),
    ModelOption(id="claude-3-opus-latest", label="Claude 3 Opus", family="claude", cli_provider="claude"),
]


class ClaudeCliProvider(BaseSubprocessCliProvider):
    provider_key = "claude"
    display_name = "Claude Code CLI"
    binary_name = "claude"

    def list_models(self) -> list[ModelOption]:
        return DEFAULT_CLAUDE_MODELS

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        self._ensure_installed()
        full_prompt = f"{req.system_prompt_markdown}\n\n---\n\n{req.task_prompt}"
        cmd = [
            "claude",
            "-p",
            full_prompt,
            "--model",
            req.model_id,
            "--dangerously-skip-permissions",
        ]

        try:
            output = self._run_cmd(cmd, cwd=req.working_dir, timeout=300)
            return CliPromptResult(
                success=True,
                output_text=output,
                raw_meta={"raw": output},
            )
        except Exception as e:
            return CliPromptResult(
                success=False,
                output_text="",
                error_message=str(e),
            )
