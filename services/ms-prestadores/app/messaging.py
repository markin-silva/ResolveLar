"""Transactional Outbox + Relay para o RabbitMQ.

Arquivo idêntico em ms-prestadores e ms-avaliacoes. Alterou? Copie para o outro.

- `registrar_evento(session, ...)`: chamado DENTRO da transação do comando (mesmo commit do agregado).
- `outbox_relay()`: task asyncio que lê eventos não publicados e publica no exchange `resolvelar.events`
  (topic, routing key = tipo) com publisher confirms. Só marca como publicado depois do ack do broker
  (entrega at-least-once; consumidores são idempotentes por eventId).
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime

import aio_pika
from sqlmodel import Session, select

from app.config import get_settings
from app.database import write_engine
from app.models import OutboxEvento, agora

logger = logging.getLogger("app.outbox")


def novo_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def envelope(ev: OutboxEvento) -> dict:
    """Envelope padrão (docs/04 / ARCHITECTURE.md)."""
    return {
        "eventId": ev.event_id,
        "tipo": ev.tipo,
        "versaoAgregado": ev.versao_agregado,
        "ocorridoEm": ev.ocorrido_em.isoformat().replace("+00:00", "Z"),
        "dados": ev.dados,
    }


def registrar_evento(session: Session, tipo: str, agregado_id: str, versao: int, dados: dict) -> OutboxEvento:
    ev = OutboxEvento(event_id=novo_event_id(), tipo=tipo, agregado_id=agregado_id,
                      versao_agregado=versao, dados=dados)
    session.add(ev)
    return ev


async def connect_rabbit() -> aio_pika.abc.AbstractRobustConnection:
    """Conecta com retry (o RabbitMQ pode demorar no primeiro boot)."""
    url = get_settings().RABBITMQ_URL
    delay = 1.0
    while True:
        try:
            return await aio_pika.connect_robust(url, timeout=5)
        except Exception as exc:
            logger.warning("RabbitMQ indisponível (%s); nova tentativa em %.0fs", type(exc).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15)


async def declare_events_exchange(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractExchange:
    return await channel.declare_exchange(get_settings().EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)


def _pendentes(limite: int = 50) -> list[OutboxEvento]:
    with Session(write_engine()) as s:
        stmt = (select(OutboxEvento).where(OutboxEvento.publicado_em.is_(None))
                .order_by(OutboxEvento.id).limit(limite))
        return list(s.exec(stmt).all())


def _marcar_publicado(ev_id: int, quando: datetime) -> None:
    with Session(write_engine()) as s:
        ev = s.get(OutboxEvento, ev_id)
        if ev and ev.publicado_em is None:
            ev.publicado_em = quando
            s.add(ev)
            s.commit()


async def outbox_relay() -> None:
    settings = get_settings()
    while True:
        try:
            connection = await connect_rabbit()
            async with connection:
                # on_return_raises + mandatory: evento sem fila ligada (consumidor ainda não subiu) NÃO é
                # descartado em silêncio; fica na outbox e é reenviado depois.
                channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
                exchange = await declare_events_exchange(channel)
                logger.info("Outbox relay conectado ao RabbitMQ")
                while True:
                    eventos = await asyncio.to_thread(_pendentes)
                    espera = settings.OUTBOX_POLL_SECONDS if not eventos else 0
                    for ev in eventos:
                        msg = aio_pika.Message(
                            body=json.dumps(envelope(ev), ensure_ascii=False).encode(),
                            content_type="application/json",
                            message_id=ev.event_id,
                            type=ev.tipo,
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        )
                        try:
                            # aguarda o confirm do broker
                            await exchange.publish(msg, routing_key=ev.tipo, mandatory=True)
                        except aio_pika.exceptions.PublishError:
                            # para no primeiro sem rota para preservar a ordem dos eventos
                            logger.warning("Sem fila ligada para %s (%s); nova tentativa em breve", ev.tipo,
                                           ev.event_id)
                            espera = settings.OUTBOX_POLL_SECONDS * 3
                            break
                        await asyncio.to_thread(_marcar_publicado, ev.id, agora())
                        logger.info("Evento publicado: %s %s (%s)", ev.tipo, ev.event_id, ev.agregado_id)
                    if espera:
                        await asyncio.sleep(espera)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no outbox relay; reiniciando em 3s")
            await asyncio.sleep(3)
