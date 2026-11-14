import os
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar
from pipeline.config import config
from pipeline.domain.exceptions import ProviderExecutionError, ProviderNotInstalledError
from pipeline.domain.ports.cli_provider import CliModelProvider


class BaseSubprocessCliProvider(CliModelProvider):
    """Base class for CLI model providers executing subprocess commands."""

    provider_key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    binary_name: ClassVar[str] = ""

    def is_installed(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def _ensure_installed(self) -> None:
        if not self.is_installed():
            raise ProviderNotInstalledError(
                f"Binary '{self.binary_name}' for provider '{self.display_name}' is not installed or not in PATH."
            )

    def _run_cmd(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        self._ensure_installed()
        actual_timeout = timeout if timeout is not None else config.CLI_TIMEOUT_SECONDS
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            result = subprocess.run(
                args,
                cwd=str(cwd) if cwd else None,
                env=full_env,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                check=False,
            )
            if result.returncode != 0:
                err_msg = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
                raise ProviderExecutionError(f"Error executing '{self.binary_name}': {err_msg}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired as e:
            raise ProviderExecutionError(f"Command '{self.binary_name}' timed out after {actual_timeout} seconds.") from e
        except Exception as e:
            if isinstance(e, ProviderExecutionError):
                raise
            raise ProviderExecutionError(f"Subprocess call failed: {e}") from e
