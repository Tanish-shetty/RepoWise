from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./repowise.db"
    llm_provider: str = "disabled"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    vector_db: str = "memory"
    github_token: str = ""
    sandbox_timeout: int = 60
    max_repository_size_mb: int = 200
    max_file_size_kb: int = 512
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    workspace_root: Path = Path(".repowise/workspaces")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

