"""Etapas duráveis da SAGA: cada tick avança uma SAGA em uma única transação local.

Caminho feliz:  RESERVAR -> PAGAR -> AGUARDAR_EVENTO -> CONFIRMAR_RESERVA -> CONFIRMAR_SOLICITACAO
Compensações:   ESTORNAR -> LIBERAR -> CANCELAR_SOLICITACAO      (pagamento recusado, conflito, falha)
                ABORTAR                                            (falha técnica ao iniciar a contratação)
"""
import asyncio
import json
import time

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app import participantes as p
from app.broker import connect, topology
from app.core import engine, lock, log, repeat
from app.models import Inbox, Saga

ESPERA_INICIO_SEGUNDOS = 30  # SAGA presa em INICIAR (o processo caiu no meio da requisição) é abortada


def compensar(saga, motivo, etapa):
    saga.motivo = saga.motivo or motivo
    saga.status, saga.etapa = "COMPENSACAO_PENDENTE", etapa


def step(saga, client):
    if saga.etapa == "INICIAR":
        # A requisição que criou a SAGA não terminou (queda do processo): desfaz o que possa ter sido feito.
        compensar(saga, "Contratação interrompida; tente novamente", "ABORTAR")
    elif saga.etapa == "RESERVAR":
        try:
            reservation = p.call(client, "POST", p.AGENDA, "/v1/reservas", {
                "sagaId": saga.id, "solicitacaoId": saga.solicitacaoId,
                "prestadorId": saga.prestadorId, "inicio": saga.inicio, "fim": saga.fim})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise
            compensar(saga, "Horário indisponível", "CANCELAR_SOLICITACAO")  # nada reservado, nada cobrado
            return
        saga.reservaId = reservation["reservaId"]
        saga.etapa = "PAGAR"
    elif saga.etapa == "PAGAR":
        # Consulta antes de repetir: timeout/queda pode ocorrer depois de uma cobrança efetiva.
        response = client.get(p.PAGAMENTOS + f"/v1/pagamentos/por-saga/{saga.id}")
        if response.status_code == 404:
            payment = p.call(client, "POST", p.PAGAMENTOS, "/v1/pagamentos", {
                "sagaId": saga.id, "solicitacaoId": saga.solicitacaoId,
                "valorCentavos": saga.valorCentavos, "meioPagamentoId": saga.meioPagamentoId})
        else:
            response.raise_for_status()
            payment = response.json()
        saga.pagamentoId = payment["pagamentoId"]
        saga.etapa = "AGUARDAR_EVENTO"  # o resultado chega pelo evento da outbox do ms-pagamentos
    elif saga.etapa == "AGUARDAR_EVENTO":
        if saga.resultadoPagamento == "APROVADO":
            saga.etapa = "CONFIRMAR_RESERVA"
        elif saga.resultadoPagamento == "RECUSADO":
            compensar(saga, "Pagamento não autorizado", "LIBERAR")
    elif saga.etapa == "CONFIRMAR_RESERVA":
        try:
            p.call(client, "POST", p.AGENDA, f"/v1/reservas/{saga.reservaId}/confirmacao")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 409):
                raise  # indisponibilidade transitória: repetir (a confirmação é idempotente)
            compensar(saga, "Reserva não pôde ser confirmada; estorno necessário", "ESTORNAR")
            return
        saga.etapa = "CONFIRMAR_SOLICITACAO"
    elif saga.etapa == "CONFIRMAR_SOLICITACAO":
        try:
            p.call(client, "POST", p.SOLICITACOES, f"/v1/orcamentos/{saga.orcamentoId}/contratacao/confirmacao",
                   {"sagaId": saga.id})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 409):
                raise
            compensar(saga, "Solicitação não pôde ser confirmada; estorno necessário", "ESTORNAR")
            return
        saga.status, saga.etapa = "CONCLUIDA", "FINALIZADA"
    elif saga.etapa == "ESTORNAR":
        payment = p.call(client, "POST", p.PAGAMENTOS, f"/v1/pagamentos/{saga.pagamentoId}/estorno")
        if payment["status"] not in ("ESTORNADO", "CANCELADO", "RECUSADO"):
            raise RuntimeError("Estorno ainda não confirmado")
        saga.etapa = "LIBERAR"
    elif saga.etapa == "LIBERAR":
        try:
            p.call(client, "POST", p.AGENDA, f"/v1/reservas/{saga.reservaId}/liberacao")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise  # reserva comprovadamente inexistente não mantém horário bloqueado
        saga.etapa = "CANCELAR_SOLICITACAO"
    elif saga.etapa in ("CANCELAR_SOLICITACAO", "ABORTAR"):
        p.call(client, "POST", p.SOLICITACOES, f"/v1/orcamentos/{saga.orcamentoId}/contratacao/cancelamento",
               {"sagaId": saga.id, "motivo": saga.motivo})
        saga.status = "COMPENSADA" if saga.etapa == "CANCELAR_SOLICITACAO" else "ABORTADA"
        saga.etapa = "FINALIZADA"


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
            with p.client(saga.correlationId) as client:
                step(saga, client)
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
                    raise  # reconexão com espera; não cria loop quente em falha do banco
                else:
                    await message.ack()  # somente depois do commit da inbox e da SAGA


async def consume():
    await repeat(consume_connection)
