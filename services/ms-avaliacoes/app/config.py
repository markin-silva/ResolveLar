from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "ms-avaliacoes"
    DATABASE_URL: str = ""
    RABBITMQ_URL: str = ""
    EVENTS_EXCHANGE: str = "resolvelar.events"
    OUTBOX_POLL_SECONDS: float = 1.0
    # Registra algumas avaliações de exemplo (geram AvaliacaoRegistrada -> notaMedia no ms-prestadores)
    SEED_DEMO_DATA: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
