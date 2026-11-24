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


# O estado da SAGA de contratação não fica aqui: ele pertence ao orquestrador-saga (banco próprio).
# Este serviço guarda só o domínio; `Solicitacao.sagaId` indica qual SAGA está com a solicitação travada.
