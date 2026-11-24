from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Solicitacao(SQLModel, table=True):
    id: str = Field(primary_key=True)
    contratanteId: str
    categoria: str
    descricao: str
    local: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = "AGUARDANDO_ACEITE"
    prestadorId: str | None = None
    sagaId: str | None = None
    motivo: str | None = None


class Orcamento(SQLModel, table=True):
    id: str = Field(primary_key=True)
    solicitacaoId: str = Field(index=True)
    prestadorId: str
    valorCentavos: int
    descricaoServico: str
    prazoEstimadoDias: int
    duracaoMinutos: int = 60
    validoAte: str
    status: str = "PENDENTE"


class Saga(SQLModel, table=True):
    id: str = Field(primary_key=True)
    idempotencyKey: str = Field(unique=True)
    fingerprint: str
    solicitacaoId: str
    orcamentoId: str
    prestadorId: str
    valorCentavos: int
    inicio: str
    fim: str
    meioPagamentoId: str
    correlationId: str
    status: str = "EM_ANDAMENTO"
    etapa: str = "RESERVAR"
    reservaId: str | None = None
    pagamentoId: str | None = None
    resultadoPagamento: str | None = None
    motivo: str | None = None
    tentativas: int = 0
    proximaTentativa: float = Field(default=0, index=True)


class Inbox(SQLModel, table=True):
    eventId: str = Field(primary_key=True)
