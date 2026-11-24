"""Etapas duráveis: cada tick confirma uma única transação local."""
import asyncio
import json
import os
import time

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app.broker import connect, topology
from app.core import engine, lock, log, repeat, require
from app.models import Inbox, Orcamento, Saga, Solicitacao

AGENDA = os.getenv("MS_AGENDAMENTOS_URL", "http://ms-agendamentos:8000")
PAGAMENTOS = os.getenv("MS_PAGAMENTOS_URL", "http://ms-pagamentos:8000")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "3"))


def call(client, method, base, path, body=None):
    response = client.request(method, base + path, json=body)
    response.raise_for_status()
    return response.json()


def finish(session, saga, success):
    lock(session, "sol:" + saga.solicitacaoId)
    sol = require(session, Solicitacao, saga.solicitacaoId)
    quote = require(session, Orcamento, saga.orcamentoId)
    sol.status = "CONFIRMADA" if success else "AGUARDANDO_ACEITE"
    sol.prestadorId = saga.prestadorId if success else None
    sol.motivo = saga.motivo
    quote.status = "APROVADO" if success else "PENDENTE"
    saga.status = "CONCLUIDA" if success else "COMPENSADA"
    saga.etapa = "FINALIZADA"
    session.add_all([sol, quote])


def step(session, saga, client):
    if saga.etapa == "RESERVAR":
        try:
            reservation = call(client, "POST", AGENDA, "/v1/reservas", {
                "sagaId": saga.id, "solicitacaoId": saga.solicitacaoId,
                "prestadorId": saga.prestadorId, "inicio": saga.inicio, "fim": saga.fim})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise
            saga.motivo = "Horário indisponível"
            finish(session, saga, False)
            return
        saga.reservaId = reservation["reservaId"]
        saga.etapa = "PAGAR"
    elif saga.etapa == "PAGAR":
        # Consulta antes de repetir: timeout/crash pode ocorrer depois de uma cobrança efetiva.
        response = client.get(PAGAMENTOS + f"/v1/pagamentos/por-saga/{saga.id}")
        if response.status_code == 404:
            payment = call(client, "POST", PAGAMENTOS, "/v1/pagamentos", {
                "sagaId": saga.id, "solicitacaoId": saga.solicitacaoId,
                "valorCentavos": saga.valorCentavos, "meioPagamentoId": saga.meioPagamentoId})
        else:
            response.raise_for_status()
            payment = response.json()
        saga.pagamentoId = payment["pagamentoId"]
        # Resultado de negócio é aplicado pelo consumidor da outbox.
        saga.etapa = "AGUARDAR_EVENTO"
    elif saga.etapa == "AGUARDAR_EVENTO":
        if saga.resultadoPagamento == "APROVADO":
            saga.etapa = "CONFIRMAR"
        elif saga.resultadoPagamento == "RECUSADO":
            saga.status = "COMPENSACAO_PENDENTE"
            saga.etapa = "LIBERAR"
    elif saga.etapa == "CONFIRMAR":
        try:
            call(client, "POST", AGENDA, f"/v1/reservas/{saga.reservaId}/confirmacao")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 409):
                raise  # Indisponibilidade transitória: repetir, inclusive confirmação já efetivada.
            saga.motivo = "Reserva não pôde ser confirmada; estorno necessário"
            saga.status, saga.etapa = "COMPENSACAO_PENDENTE", "ESTORNAR"
            return
        finish(session, saga, True)
    elif saga.etapa == "ESTORNAR":
        payment = call(client, "POST", PAGAMENTOS, f"/v1/pagamentos/{saga.pagamentoId}/estorno")
        if payment["status"] not in ("ESTORNADO", "CANCELADO", "RECUSADO"):
            raise RuntimeError("Estorno ainda não confirmado")
        saga.etapa = "LIBERAR"
    elif saga.etapa == "LIBERAR":
        try:
            call(client, "POST", AGENDA, f"/v1/reservas/{saga.reservaId}/liberacao")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            # Reserva comprovadamente inexistente não mantém horário bloqueado.
        finish(session, saga, False)


def tick():
    # SKIP LOCKED permite réplicas; HTTP roda em thread, sem bloquear o consumidor asyncio.
    with Session(engine) as session, session.begin():
        saga = session.exec(select(Saga).where(Saga.etapa != "FINALIZADA",
                                               Saga.proximaTentativa <= time.time())
                            .order_by(Saga.proximaTentativa)
                            .with_for_update(skip_locked=True).limit(1)).first()
        if not saga:
            return
        try:
            with httpx.Client(timeout=TIMEOUT, headers={"X-Correlation-Id": saga.correlationId}) as client:
                step(session, saga, client)
            saga.tentativas = 0
            saga.proximaTentativa = time.time() + (2 if saga.etapa == "AGUARDAR_EVENTO" else 0)
        except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
            saga.tentativas += 1
            saga.proximaTentativa = time.time() + min(60, 2 ** min(saga.tentativas, 6))
            log.exception("Retry sagaId=%s etapa=%s correlationId=%s", saga.id, saga.etapa, saga.correlationId)
        session.add(saga)
        log.info("SAGA sagaId=%s etapa=%s status=%s correlationId=%s",
                 saga.id, saga.etapa, saga.status, saga.correlationId)


async def orchestrate():
    async def run():
        await asyncio.to_thread(tick)
    await repeat(run)


class PaymentData(BaseModel):
    sagaId: str
    solicitacaoId: str
    pagamentoId: str
    valorCentavos: int
    motivo: str | None = None


class PaymentEvent(BaseModel):
    eventId: str = Field(min_length=1)
    tipo: str = Field(pattern="^Pagamento(Aprovado|Recusado)$")
    versaoAgregado: int = Field(ge=1)
    ocorridoEm: str
    dados: PaymentData


def record_event(event):
    with Session(engine) as session, session.begin():
        lock(session, "event:" + event.eventId)
        if session.get(Inbox, event.eventId):
            return
        saga = session.exec(select(Saga).where(Saga.id == event.dados.sagaId).with_for_update()).first()
        if saga is None:
            raise ValueError("SAGA desconhecida")
        result = "APROVADO" if event.tipo == "PagamentoAprovado" else "RECUSADO"
        if (event.dados.solicitacaoId != saga.solicitacaoId or event.dados.valorCentavos != saga.valorCentavos
                or (saga.pagamentoId and saga.pagamentoId != event.dados.pagamentoId)
                or (saga.resultadoPagamento and saga.resultadoPagamento != result)):
            raise ValueError("Evento incompatível com a SAGA")
        if saga.etapa != "FINALIZADA":
            saga.pagamentoId = event.dados.pagamentoId
            saga.resultadoPagamento = result
            saga.motivo = event.dados.motivo
            saga.proximaTentativa = 0
            session.add(saga)
        session.add(Inbox(eventId=event.eventId))


async def consume_connection():
    connection = await connect()
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        _, queue = await topology(channel)
        async with queue.iterator() as messages:
            async for message in messages:
                try:
                    event = PaymentEvent.model_validate_json(message.body)
                    await asyncio.to_thread(record_event, event)
                except (ValidationError, ValueError, json.JSONDecodeError):
                    log.exception("Evento inválido enviado para DLQ")
                    await message.reject(requeue=False)
                except Exception:
                    await message.nack(requeue=True)
                    raise  # Reconexão com espera; não cria loop quente em falha do banco.
                else:
                    await message.ack()  # Somente depois do commit da inbox e da SAGA.


async def consume():
    await repeat(consume_connection)
