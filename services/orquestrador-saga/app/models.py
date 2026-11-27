"""Estado do orquestrador. Nada de domínio aqui: pedidos e orçamentos ficam no ms-solicitacoes,
reservas no ms-agendamentos e cobranças no ms-pagamentos. Este banco guarda só o andamento de cada SAGA
(para retomar depois de um reinício) e os eventos já processados (inbox)."""
from sqlmodel import Field, SQLModel


class Saga(SQLModel, table=True):
    id: str = Field(primary_key=True)
    idempotencyKey: str = Field(unique=True)
    fingerprint: str
    contratanteId: str
    orcamentoId: str
    inicio: str
    meioPagamentoId: str
    correlationId: str
    # preenchidos pelo ms-solicitacoes quando a contratação é iniciada
    solicitacaoId: str | None = None
    prestadorId: str | None = None
    valorCentavos: int | None = None
    fim: str | None = None
    # EM_ANDAMENTO | COMPENSACAO_PENDENTE | CONCLUIDA | COMPENSADA | REJEITADA | ABORTADA
    status: str = "EM_ANDAMENTO"
    # INICIAR | RESERVAR | PAGAR | AGUARDAR_EVENTO | CONFIRMAR_RESERVA | CONFIRMAR_SOLICITACAO
    # | ESTORNAR | LIBERAR | CANCELAR_SOLICITACAO | ABORTAR | FINALIZADA
    etapa: str = "INICIAR"
    reservaId: str | None = None
    pagamentoId: str | None = None
    resultadoPagamento: str | None = None
    motivo: str | None = None
    erroStatus: int | None = None  # resposta guardada de uma aprovação rejeitada (replay idempotente)
    tentativas: int = 0
    proximaTentativa: float = Field(default=0, index=True)


class Inbox(SQLModel, table=True):
    eventId: str = Field(primary_key=True)
