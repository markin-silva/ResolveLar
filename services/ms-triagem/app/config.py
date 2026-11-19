from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Modelo e preço padrão por provedor (USD por 1 milhão de tokens). Preços mudam: confira a página
# do provedor e sobrescreva com LLM_PRICE_INPUT_PER_MTOK / LLM_PRICE_OUTPUT_PER_MTOK.
DEFAULTS = {
    "gemini": {"model": "gemini-3.5-flash-lite", "in": 0.30, "out": 2.50},
    "openai": {"model": "gpt-4o-mini", "in": 0.15, "out": 0.60},
}


def _chave_valida(key: str) -> bool:
    return bool(key) and not key.startswith("your_")


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (sem valores sensíveis hardcoded)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "ms-triagem"
    REDIS_URL: str = ""
    MS_PRESTADORES_URL: str = "http://ms-prestadores:8000"

    # --- LLM ---
    LLM_PROVIDER: str = "auto"  # auto | gemini | openai | none
    LLM_MODEL: str = ""
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_PRICE_INPUT_PER_MTOK: float | None = None
    LLM_PRICE_OUTPUT_PER_MTOK: float | None = None

    # --- Resiliência ---
    LLM_TIMEOUT_SECONDS: float = 4.5        # por tentativa
    LLM_MAX_RETRIES: int = 1                # tentativas extras (backoff exponencial)
    LLM_TOTAL_BUDGET_SECONDS: float = 5.0   # teto somando as tentativas (o Kong corta em 10s)
    TOOL_TIMEOUT_SECONDS: float = 2.0
    TOOL_MAX_RETRIES: int = 1
    CIRCUIT_FAILURE_THRESHOLD: int = 3      # falhas seguidas do LLM que abrem o circuito
    CIRCUIT_RESET_SECONDS: float = 30.0
    CACHE_TTL_SECONDS: int = 3600

    # --- RAG ---
    CHROMA_PATH: str = "/data/chroma"
    RAG_TOP_K: int = 4

    def provider(self) -> str:
        p = self.LLM_PROVIDER.lower()
        if p == "auto":
            if _chave_valida(self.GEMINI_API_KEY):
                return "gemini"
            if _chave_valida(self.OPENAI_API_KEY):
                return "openai"
            return "none"
        if p == "gemini" and not _chave_valida(self.GEMINI_API_KEY):
            return "none"
        if p == "openai" and not _chave_valida(self.OPENAI_API_KEY):
            return "none"
        return p if p in DEFAULTS else "none"

    def model(self) -> str | None:
        p = self.provider()
        return (self.LLM_MODEL or DEFAULTS[p]["model"]) if p in DEFAULTS else None

    def precos(self) -> tuple[float, float]:
        d = DEFAULTS.get(self.provider(), {"in": 0.0, "out": 0.0})
        return (self.LLM_PRICE_INPUT_PER_MTOK if self.LLM_PRICE_INPUT_PER_MTOK is not None else d["in"],
                self.LLM_PRICE_OUTPUT_PER_MTOK if self.LLM_PRICE_OUTPUT_PER_MTOK is not None else d["out"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
