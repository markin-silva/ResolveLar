from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacao"
    __table_args__ = (CheckConstraint("nota BETWEEN 1 AND 5", name="ck_avaliacao_nota"),)

    id: str = Field(primary_key=True)
    # uma avaliação por solicitação (POST repetido -> 409)
    solicitacao_id: str = Field(unique=True)
    prestador_id: str = Field(index=True)
    contratante_id: str
    nota: int
    comentario: str | None = None
    criada_em: datetime = Field(default_factory=agora)


class ReputacaoPrestador(SQLModel, table=True):
    """Agregado de reputação por prestador. Travado com SELECT ... FOR UPDATE a cada avaliação, então
    `total` cresce sem buracos e serve de `versaoAgregado` do evento AvaliacaoRegistrada."""

    __tablename__ = "reputacao_prestador"

    prestador_id: str = Field(primary_key=True)
    soma_notas: int = 0
    total: int = 0


class OutboxEvento(SQLModel, table=True):
    __tablename__ = "outbox"

    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True)
    tipo: str
    agregado_id: str = Field(index=True)
    versao_agregado: int
    ocorrido_em: datetime = Field(default_factory=agora)
    dados: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    publicado_em: datetime | None = Field(default=None, index=True)
