"""Modelos do CQRS (docs/04, seção 3).

- Escrita (db-prestadores-write): agregado `prestador` normalizado + tabela `outbox`.
- Leitura (db-prestadores-read): `prestador_view` desnormalizada (pronta para a tela de busca)
  + `evento_processado` (idempotência do projetor por eventId).
"""
from datetime import datetime, timezone

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def agora() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ escrita
class Prestador(SQLModel, table=True):
    __tablename__ = "prestador"

    id: str = Field(primary_key=True)
    nome: str
    email: str | None = Field(default=None, unique=True)
    telefone: str | None = None
    foto_url: str | None = None
    categorias: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    cidade: str
    uf: str
    bairros_atendidos: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    lat: float | None = None
    lon: float | None = None
    raio_atendimento_km: int = 10
    preco_medio_centavos: int | None = None
    ativo: bool = True
    versao: int = 1
    criado_em: datetime = Field(default_factory=agora)
    atualizado_em: datetime = Field(default_factory=agora)


class OutboxEvento(SQLModel, table=True):
    """Evento gravado na MESMA transação do comando; o relay publica no RabbitMQ depois."""

    __tablename__ = "outbox"

    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True)
    tipo: str
    agregado_id: str = Field(index=True)
    versao_agregado: int
    ocorrido_em: datetime = Field(default_factory=agora)
    dados: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    publicado_em: datetime | None = Field(default=None, index=True)


# ------------------------------------------------------------------ leitura
class PrestadorView(SQLModel, table=True):
    """Documento desnormalizado (docs/04, 3.4). Campos de reputação vêm de outros serviços via eventos."""

    __tablename__ = "prestador_view"

    prestador_id: str = Field(primary_key=True)
    nome: str = ""
    foto_url: str | None = None
    categorias: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    cidade: str = Field(default="", index=True)
    uf: str = ""
    bairros_atendidos: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    lat: float | None = None
    lon: float | None = None
    raio_atendimento_km: int = 10
    nota_media: float = 0.0
    total_avaliacoes: int = 0
    servicos_concluidos: int = 0
    disponivel_hoje: bool = True
    preco_medio_centavos: int | None = None
    ativo: bool = False
    # versão do agregado Prestador já aplicada (0 = linha criada por evento de outro serviço antes do cadastro)
    versao: int = 0
    # versão da reputação (totalAvaliacoes) já aplicada: ignora AvaliacaoRegistrada antigos/duplicados
    versao_avaliacoes: int = 0
    atualizado_em: datetime = Field(default_factory=agora)


class EventoProcessado(SQLModel, table=True):
    __tablename__ = "evento_processado"

    event_id: str = Field(primary_key=True)
    tipo: str
    processado_em: datetime = Field(default_factory=agora)


WRITE_TABLES = [Prestador.__table__, OutboxEvento.__table__]
READ_TABLES = [PrestadorView.__table__, EventoProcessado.__table__]
