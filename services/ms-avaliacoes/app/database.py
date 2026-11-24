import logging
import time
from functools import lru_cache

from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger("app")


@lru_cache
def write_engine():
    """Nome igual ao do ms-prestadores para o app/messaging.py ser idêntico nos dois serviços."""
    url = get_settings().DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    return create_engine(url, pool_pre_ping=True)


def create_schema(attempts: int = 10) -> None:
    from app import models  # noqa: F401 (registra as tabelas)

    for attempt in range(1, attempts + 1):
        try:
            SQLModel.metadata.create_all(write_engine())
            return
        except OperationalError as exc:  # banco ainda subindo
            if attempt == attempts:
                raise
            logger.warning("Banco indisponível (%s), tentativa %s/%s", type(exc).__name__, attempt, attempts)
            time.sleep(2)
