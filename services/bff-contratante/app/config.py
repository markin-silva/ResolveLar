from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tudo vem de variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "bff-contratante"
    HTTP_TIMEOUT_SECONDS: float = 3.0
    # true: se um microsserviço de domínio ainda não existe (erro de rede), devolve payloads de exemplo.
    ENABLE_UPSTREAM_MOCK: bool = False

    MS_PRESTADORES_URL: str = "http://ms-prestadores:8000"
    MS_SOLICITACOES_URL: str = "http://ms-solicitacoes:8000"
    MS_PAGAMENTOS_URL: str = "http://ms-pagamentos:8000"
    MS_AVALIACOES_URL: str = "http://ms-avaliacoes:8000"
    MS_TRIAGEM_URL: str = "http://ms-triagem:8000"
    # A triagem chama um LLM: timeout maior que o padrão (o ms-triagem corta o LLM em ~6s e cai no
    # fallback). Deve ficar abaixo do read_timeout do Kong (10s).
    TRIAGEM_TIMEOUT_SECONDS: float = 9.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
