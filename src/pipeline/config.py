from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def compute_celery_timeouts(
    agent_timeout_seconds: int,
    overhead_seconds: int = 120,
    grace_seconds: int = 60,
) -> tuple[int, int]:
    """Derive Celery soft and hard timeouts from the agent timeout.

    The Celery timeouts must always exceed ``agent_timeout_seconds`` to account for
    surrounding orchestration steps (database operations, board API comments/moves,
    and worker teardown).
    """
    safe_agent_timeout = max(int(agent_timeout_seconds), 1)
    safe_overhead = max(int(overhead_seconds), 30)
    safe_grace = max(int(grace_seconds), 30)
    soft_limit = safe_agent_timeout + safe_overhead
    hard_limit = soft_limit + safe_grace
    return soft_limit, hard_limit


class Config(BaseSettings):
    DATABASE_URL: str = "sqlite:///data/pipeline.db"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # Timeout para execuções de agentes de IA nas CLIs (em segundos, padrão 10 minutos)
    CLI_TIMEOUT_SECONDS: int = 600

    # Configurações do Celery (broker, backend, agendamento automático e folga de timeout)
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_PIPELINE_INTERVAL_SECONDS: int = 60
    CELERY_TIMEOUT_OVERHEAD_SECONDS: int = 120
    CELERY_HARD_TIMEOUT_GRACE_SECONDS: int = 60
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Default provider secrets/keys (opcionais, fallback se não informados no DB)
    GITHUB_TOKEN: str | None = None
    GITHUB_OWNER: str | None = None

    JIRA_BASE_URL: str | None = None
    JIRA_EMAIL: str | None = None
    JIRA_API_TOKEN: str | None = None

    TRELLO_API_KEY: str | None = None
    TRELLO_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def celery_soft_time_limit(self) -> int:
        soft_limit, _ = compute_celery_timeouts(
            self.CLI_TIMEOUT_SECONDS,
            self.CELERY_TIMEOUT_OVERHEAD_SECONDS,
            self.CELERY_HARD_TIMEOUT_GRACE_SECONDS,
        )
        return soft_limit

    @property
    def celery_time_limit(self) -> int:
        _, hard_limit = compute_celery_timeouts(
            self.CLI_TIMEOUT_SECONDS,
            self.CELERY_TIMEOUT_OVERHEAD_SECONDS,
            self.CELERY_HARD_TIMEOUT_GRACE_SECONDS,
        )
        return hard_limit

    def setup_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
config.setup_dirs()
