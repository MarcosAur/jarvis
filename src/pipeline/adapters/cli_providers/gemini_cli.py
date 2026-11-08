from pipeline.adapters.cli_providers.base import BaseSubprocessCliProvider
from pipeline.domain.entities import CliPromptRequest, CliPromptResult, ModelOption

DEFAULT_GEMINI_MODELS = [
    ModelOption(id="gemini-2.5-pro", label="Gemini 2.5 Pro", family="gemini", cli_provider="gemini"),
    ModelOption(id="gemini-2.5-flash", label="Gemini 2.5 Flash", family="gemini", cli_provider="gemini"),
    ModelOption(id="gemini-1.5-pro", label="Gemini 1.5 Pro", family="gemini", cli_provider="gemini"),
    ModelOption(id="gemini-1.5-flash", label="Gemini 1.5 Flash", family="gemini", cli_provider="gemini"),
]


class GeminiCliProvider(BaseSubprocessCliProvider):
    provider_key = "gemini"
    display_name = "Google Gemini CLI"
    binary_name = "gemini"

    def list_models(self) -> list[ModelOption]:
        return DEFAULT_GEMINI_MODELS

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        self._ensure_installed()
        full_prompt = f"{req.system_prompt_markdown}\n\n---\n\n{req.task_prompt}"
        cmd = [
            "gemini",
            "-p",
            full_prompt,
            "-m",
            req.model_id,
            "--yolo",
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
