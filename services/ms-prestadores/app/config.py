from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "ms-prestadores"
    # CQRS: um banco para comandos (escrita) e outro para consultas (leitura desnormalizada)
    DATABASE_URL_WRITE: str = ""
    DATABASE_URL_READ: str = ""
    RABBITMQ_URL: str = ""
    REDIS_URL: str = ""

    EVENTS_EXCHANGE: str = "resolvelar.events"
    DLX_EXCHANGE: str = "resolvelar.dlx"
    OUTBOX_POLL_SECONDS: float = 1.0
    PROJECTOR_MAX_RETRIES: int = 3
    CACHE_TTL_SECONDS: int = 60
    SEARCH_CACHE_TTL_SECONDS: int = 30
    # Cadastra prestadores de exemplo (via comandos, gerando eventos) se o banco de escrita estiver vazio
    SEED_DEMO_DATA: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
