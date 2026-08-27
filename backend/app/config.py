"""Application settings, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Living Docs backend."""

    model_config = SettingsConfigDict(env_prefix="LIVING_DOCS_")

    database_url: str = "sqlite:///./living_docs.db"
    static_dir: str = "static"


@lru_cache
def get_settings() -> Settings:
    return Settings()
