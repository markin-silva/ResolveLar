"""Projetor do modelo de leitura (docs/04, 3.5): consome eventos do RabbitMQ e atualiza prestador_view.

Idempotência:
- `eventId` já processado -> ignora (tabela evento_processado, no MESMO commit da projeção);
- eventos do agregado Prestador com `versaoAgregado <= versao` aplicada -> ignora;
- `AvaliacaoRegistrada` com `versaoAgregado` (= totalAvaliacoes do prestador) <= versao_avaliacoes -> ignora.

Falhas: até PROJECTOR_MAX_RETRIES tentativas com backoff; depois a mensagem vai para a DLQ
(`ms-prestadores.projecao.dlq`, via dead-letter exchange `resolvelar.dlx`).
"""
import asyncio
import json
import logging

import aio_pika
from sqlmodel import Session

from app import cache
from app.config import get_settings
from app.database import read_engine
from app.messaging import connect_rabbit, declare_events_exchange
from app.models import EventoProcessado, PrestadorView, agora

logger = logging.getLogger("app.projetor")

QUEUE = "ms-prestadores.projecao"
EVENTOS_PRESTADOR = {"PrestadorCadastrado", "PerfilPrestadorAtualizado", "AreasAtendimentoAlteradas",
                     "PrestadorDesativado"}
EVENTOS_EXTERNOS = {"AvaliacaoRegistrada", "ServicoConcluido", "DisponibilidadeAlterada"}

# camelCase do evento -> coluna da view
CAMPOS = {
    "nome": "nome", "fotoUrl": "foto_url", "categorias": "categorias", "cidade": "cidade", "uf": "uf",
    "bairrosAtendidos": "bairros_atendidos", "raioAtendimentoKm": "raio_atendimento_km",
    "precoMedioCentavos": "preco_medio_centavos", "ativo": "ativo",
}


def aplicar_evento(evento: dict) -> str | None:
    """Aplica um evento ao Read DB. Retorna o prestadorId alterado (para invalidar o cache) ou None."""
    event_id, tipo = evento["eventId"], evento["tipo"]
    versao = int(evento.get("versaoAgregado") or 0)
    dados = evento.get("dados") or {}
    prestador_id = dados.get("prestadorId")
    if not prestador_id:
        raise ValueError(f"evento {event_id} sem dados.prestadorId")

    with Session(read_engine()) as s:
        if s.get(EventoProcessado, event_id):
            return None  # duplicado (at-least-once)

        view = s.get(PrestadorView, prestador_id, with_for_update=True)
        alterou = True
        if view is None:
            # pode chegar evento de outro serviço antes do cadastro: cria a linha (versao=0, inativa)
            view = PrestadorView(prestador_id=prestador_id)

        if tipo in EVENTOS_PRESTADOR:
            if versao <= view.versao:
                alterou = False  # evento antigo/fora de ordem
            else:
                for chave, coluna in CAMPOS.items():
                    if chave in dados:
                        setattr(view, coluna, dados[chave])
                if "localizacao" in dados and dados["localizacao"]:
                    view.lat = dados["localizacao"].get("lat")
                    view.lon = dados["localizacao"].get("lon")
                if tipo == "PrestadorCadastrado":
                    view.ativo = True
                elif tipo == "PrestadorDesativado":
                    view.ativo = False
                view.versao = versao
        elif tipo == "AvaliacaoRegistrada":
            if versao <= view.versao_avaliacoes:
                alterou = False
            else:
                view.nota_media = float(dados["notaMedia"])
                view.total_avaliacoes = int(dados["totalAvaliacoes"])
                view.versao_avaliacoes = versao
        elif tipo == "ServicoConcluido":
            view.servicos_concluidos += 1  # idempotente pelo eventId
        elif tipo == "DisponibilidadeAlterada":
            view.disponivel_hoje = bool(dados.get("disponivelHoje", True))
        else:
            alterou = False

        if alterou:
            view.atualizado_em = agora()
            s.add(view)
        s.add(EventoProcessado(event_id=event_id, tipo=tipo))
        s.commit()
        return prestador_id if alterou else None


async def _processar(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
    settings = get_settings()
    try:
        evento = json.loads(msg.body)
        evento["eventId"], evento["tipo"]
    except Exception:
        logger.error("Mensagem inválida descartada para a DLQ: %r", msg.body[:200])
        await msg.reject(requeue=False)
        return

    for tentativa in range(1, settings.PROJECTOR_MAX_RETRIES + 1):
        try:
            prestador_id = await asyncio.to_thread(aplicar_evento, evento)
            break
        except Exception as exc:
            logger.warning("Falha ao projetar %s %s (tentativa %s/%s): %s", evento["tipo"], evento["eventId"],
                           tentativa, settings.PROJECTOR_MAX_RETRIES, exc)
            if tentativa == settings.PROJECTOR_MAX_RETRIES:
                await msg.reject(requeue=False)  # -> DLQ
                return
            await asyncio.sleep(0.5 * 2 ** tentativa)

    if prestador_id:
        await asyncio.to_thread(cache.invalidar, prestador_id)
        logger.info("Projeção atualizada: %s %s -> %s", evento["tipo"], evento["eventId"], prestador_id)
    await msg.ack()


async def run_projector() -> None:
    settings = get_settings()
    while True:
        try:
            connection = await connect_rabbit()
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)
                exchange = await declare_events_exchange(channel)
                dlx = await channel.declare_exchange(settings.DLX_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
                dlq = await channel.declare_queue(f"{QUEUE}.dlq", durable=True)
                await dlq.bind(dlx, routing_key=QUEUE)
                queue = await channel.declare_queue(QUEUE, durable=True, arguments={
                    "x-dead-letter-exchange": settings.DLX_EXCHANGE,
                    "x-dead-letter-routing-key": QUEUE,
                })
                for tipo in sorted(EVENTOS_PRESTADOR | EVENTOS_EXTERNOS):
                    await queue.bind(exchange, routing_key=tipo)
                logger.info("Projetor consumindo a fila %s", QUEUE)
                async with queue.iterator() as it:
                    async for msg in it:
                        await _processar(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no projetor; reiniciando em 3s")
            await asyncio.sleep(3)
