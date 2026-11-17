from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "service"
    DATABASE_URL: str = ""
    RABBITMQ_URL: str = ""
    REDIS_URL: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
