from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tudo vem de variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "bff-prestador"
    HTTP_TIMEOUT_SECONDS: float = 3.0
    # true: se um microsserviço de domínio ainda não existe (erro de rede), devolve payloads de exemplo.
    ENABLE_UPSTREAM_MOCK: bool = False

    MS_SOLICITACOES_URL: str = "http://ms-solicitacoes:8000"
    MS_AGENDAMENTOS_URL: str = "http://ms-agendamentos:8000"
    MS_PAGAMENTOS_URL: str = "http://ms-pagamentos:8000"
    MS_PRESTADORES_URL: str = "http://ms-prestadores:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
