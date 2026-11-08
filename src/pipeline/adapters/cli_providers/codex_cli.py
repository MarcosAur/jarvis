from pipeline.adapters.cli_providers.base import BaseSubprocessCliProvider
from pipeline.domain.entities import CliPromptRequest, CliPromptResult, ModelOption

DEFAULT_CODEX_MODELS = [
    ModelOption(id="o3-mini", label="OpenAI o3-mini", family="openai", cli_provider="codex"),
    ModelOption(id="o3", label="OpenAI o3", family="openai", cli_provider="codex"),
    ModelOption(id="o1", label="OpenAI o1", family="openai", cli_provider="codex"),
    ModelOption(id="gpt-4o", label="GPT-4o", family="openai", cli_provider="codex"),
]


class CodexCliProvider(BaseSubprocessCliProvider):
    provider_key = "codex"
    display_name = "OpenAI Codex CLI"
    binary_name = "codex"

    def list_models(self) -> list[ModelOption]:
        return DEFAULT_CODEX_MODELS

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        self._ensure_installed()
        full_prompt = f"{req.system_prompt_markdown}\n\n---\n\n{req.task_prompt}"
        cmd = [
            "codex",
            "-m",
            req.model_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "-a",
            "never",
            full_prompt,
        ]

        try:
            output = self._run_cmd(cmd, cwd=req.working_dir)
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
