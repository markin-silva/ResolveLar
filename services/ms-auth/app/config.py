from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "ms-auth"
    # Mesmo segredo com que o Kong valida o JWT. Sem valor padrão: o serviço não sobe sem ele.
    JWT_SECRET: str = ""
    # Senha única dos usuários de demonstração (ver app/usuarios.py). Vem do ambiente, nunca do código.
    DEMO_PASSWORD: str = ""
    JWT_TTL_HOURS: float = 12.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
