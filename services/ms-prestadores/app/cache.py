"""Cache Redis do lado de leitura. Opcional: se o Redis cair, a consulta vai direto ao Read DB."""
import json
import logging
from functools import lru_cache
from typing import Any

import redis

from app.config import get_settings

logger = logging.getLogger("app.cache")


@lru_cache
def client() -> redis.Redis | None:
    url = get_settings().REDIS_URL
    if not url:
        return None
    return redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)


def chave_prestador(prestador_id: str) -> str:
    return f"prestador:{prestador_id}"


def get_json(key: str) -> Any | None:
    try:
        c = client()
        raw = c.get(key) if c else None
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Redis indisponível no GET (%s)", type(exc).__name__)
        return None


def set_json(key: str, value: Any, ttl: int) -> None:
    try:
        c = client()
        if c:
            c.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception as exc:
        logger.warning("Redis indisponível no SET (%s)", type(exc).__name__)


def invalidar(prestador_id: str | None) -> None:
    """Chamado pelo projetor: remove o detalhe do prestador e os caches de busca."""
    try:
        c = client()
        if not c:
            return
        if prestador_id:
            c.delete(chave_prestador(prestador_id))
        keys = list(c.scan_iter("busca:*", count=200))
        if keys:
            c.delete(*keys)
    except Exception as exc:
        logger.warning("Redis indisponível ao invalidar (%s)", type(exc).__name__)
