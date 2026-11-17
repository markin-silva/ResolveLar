from functools import lru_cache
from typing import Iterator

from sqlmodel import Session, create_engine

from app.config import get_settings


@lru_cache
def get_engine():
    """Engine criada sob demanda: o serviço sobe (e /health responde) mesmo sem banco."""
    url = get_settings().DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
