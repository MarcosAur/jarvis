from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    DATABASE_URL: str = "sqlite:///data/pipeline.db"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"

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

    def setup_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
config.setup_dirs()
