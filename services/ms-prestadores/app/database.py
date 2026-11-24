"""Dois engines (CQRS): escrita em db-prestadores-write, leitura em db-prestadores-read."""
import logging
import time
from functools import lru_cache

from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger("app")


@lru_cache
def write_engine():
    url = get_settings().DATABASE_URL_WRITE
    if not url:
        raise RuntimeError("DATABASE_URL_WRITE não configurada")
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def read_engine():
    url = get_settings().DATABASE_URL_READ
    if not url:
        raise RuntimeError("DATABASE_URL_READ não configurada")
    return create_engine(url, pool_pre_ping=True)


def create_schemas(attempts: int = 10) -> None:
    """Cria só as tabelas de cada lado em seu banco (com retry enquanto o Postgres sobe)."""
    from app.models import READ_TABLES, WRITE_TABLES

    for attempt in range(1, attempts + 1):
        try:
            SQLModel.metadata.create_all(write_engine(), tables=WRITE_TABLES)
            SQLModel.metadata.create_all(read_engine(), tables=READ_TABLES)
            return
        except OperationalError as exc:  # banco ainda subindo
            if attempt == attempts:
                raise
            logger.warning("Banco indisponível (%s), tentativa %s/%s", type(exc).__name__, attempt, attempts)
            time.sleep(2)
