import json
import re
from pathlib import Path
from pipeline.adapters.cli_providers.base import BaseSubprocessCliProvider
from pipeline.domain.entities import CliPromptRequest, CliPromptResult, ModelOption

FALLBACK_AGY_MODELS = [
    ModelOption(id="gemini-4-argon-medium", label="Gemini 4 Argon (Medium)", family="gemini", cli_provider="agy"),
    ModelOption(id="gemini-4-argon-high", label="Gemini 4 Argon (High)", family="gemini", cli_provider="agy"),
    ModelOption(id="gemini-3.8-flash-high", label="Gemini 3.8 Flash (High)", family="gemini", cli_provider="agy"),
    ModelOption(id="claude-sonnet-5-5-high", label="Claude Sonnet 5.5 (High)", family="claude", cli_provider="agy"),
    ModelOption(id="claude-opus-5-5-high", label="Claude Opus 5.5 (High)", family="claude", cli_provider="agy"),
    ModelOption(id="gpt-oss-120b-medium", label="GPT-OSS 120B (Medium)", family="gpt-oss", cli_provider="agy"),
]


class AgyCliProvider(BaseSubprocessCliProvider):
    provider_key = "agy"
    display_name = "Antigravity CLI (Assinatura Gemini)"
    binary_name = "agy"

    def list_models(self) -> list[ModelOption]:
        if not self.is_installed():
            return FALLBACK_AGY_MODELS

        try:
            raw = self._run_cmd(["agy", "models"], timeout=15)
            # Remove any spinner artifacts or non-ascii progress characters at start
            clean_lines = []
            for line in raw.splitlines():
                # Remove terminal spinner patterns like "⠋ Fetching available models..."
                cleaned = re.sub(r"^[\s\u2800-\u28ff\w\.\s]*Fetching available models\.\.\.", "", line).strip()
                if cleaned:
                    clean_lines.append(cleaned)

            models: list[ModelOption] = []
            for line in clean_lines:
                # Match: "<model_id>    <Label>"
                parts = re.split(r"\s+", line.strip(), maxsplit=1)
                if len(parts) == 2:
                    m_id, m_label = parts[0].strip(), parts[1].strip()
                elif len(parts) == 1 and parts[0]:
                    m_id = parts[0].strip()
                    m_label = m_id
                else:
                    continue

                # Determine family
                family = "general"
                if m_id.startswith("gemini"):
                    family = "gemini"
                elif m_id.startswith("claude"):
                    family = "claude"
                elif "gpt" in m_id or "openai" in m_id:
                    family = "openai"

                models.append(ModelOption(id=m_id, label=m_label, family=family, cli_provider=self.provider_key))

            return models if models else FALLBACK_AGY_MODELS
        except Exception:
            return FALLBACK_AGY_MODELS

    def execute_prompt(self, req: CliPromptRequest) -> CliPromptResult:
        self._ensure_installed()
        full_prompt = f"{req.system_prompt_markdown}\n\n---\n\n{req.task_prompt}"
        cmd = [
            "agy",
            "--print",
            full_prompt,
            "--model",
            req.model_id,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
        ]

        try:
            raw_output = self._run_cmd(cmd, cwd=req.working_dir)
            try:
                data = json.loads(raw_output)
                output_text = data.get("response") or data.get("text") or data.get("content") or raw_output
                usage = data.get("usage", {})
                tokens_in = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                tokens_out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
                return CliPromptResult(
                    success=True,
                    output_text=output_text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    raw_meta=data,
                )
            except json.JSONDecodeError:
                return CliPromptResult(
                    success=True,
                    output_text=raw_output,
                    raw_meta={"raw": raw_output},
                )
        except Exception as e:
            return CliPromptResult(
                success=False,
                output_text="",
                error_message=str(e),
            )
