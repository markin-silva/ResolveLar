"""Peças de resiliência da triagem: cache Redis (opcional) e circuit breaker do LLM."""
import json
import logging
import time
from functools import lru_cache
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("app.resiliencia")


# ------------------------------------------------------------------ cache
@lru_cache
def _redis() -> aioredis.Redis | None:
    url = get_settings().REDIS_URL
    if not url:
        return None
    return aioredis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)


async def cache_get(key: str) -> Any | None:
    try:
        r = _redis()
        raw = await r.get(key) if r else None
        return json.loads(raw) if raw else None
    except Exception as exc:  # Redis fora do ar não derruba a triagem
        logger.warning("Cache indisponível no GET (%s)", type(exc).__name__)
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        r = _redis()
        if r:
            await r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as exc:
        logger.warning("Cache indisponível no SET (%s)", type(exc).__name__)


# ------------------------------------------------------------------ circuit breaker
class CircuitBreaker:
    """FECHADO -> (N falhas seguidas) -> ABERTO -> (após reset_s) -> MEIO_ABERTO -> 1 tentativa."""

    def __init__(self, threshold: int, reset_s: float):
        self.threshold, self.reset_s = threshold, reset_s
        self.falhas = 0
        self.aberto_em: float | None = None

    @property
    def estado(self) -> str:
        if self.aberto_em is None:
            return "FECHADO"
        return "MEIO_ABERTO" if time.monotonic() - self.aberto_em >= self.reset_s else "ABERTO"

    def permite(self) -> bool:
        return self.estado != "ABERTO"

    def sucesso(self) -> None:
        self.falhas, self.aberto_em = 0, None

    def falha(self) -> None:
        self.falhas += 1
        if self.falhas >= self.threshold or self.estado == "MEIO_ABERTO":
            self.aberto_em = time.monotonic()
            logger.warning("Circuit breaker do LLM ABERTO por %.0fs", self.reset_s)
