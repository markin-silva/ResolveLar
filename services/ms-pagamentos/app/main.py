import asyncio
import json

import aio_pika
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field as InputField
from sqlalchemy import Column, JSON
from sqlmodel import Field, Session, SQLModel, select

from app.broker import connect, topology
from app.core import create_app, engine, lock, now, repeat, require, uid


class Pagamento(SQLModel, table=True):
    id: str = Field(primary_key=True)
    sagaId: str = Field(unique=True, index=True)
    solicitacaoId: str = Field(index=True)
    valorCentavos: int
    meioPagamentoId: str
    status: str
    motivo: str | None = None


class Outbox(SQLModel, table=True):
    id: str = Field(primary_key=True)
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    correlationId: str
    publicado: bool = Field(default=False, index=True)


class PagamentoIn(BaseModel):
    sagaId: str = InputField(min_length=1)
    solicitacaoId: str = InputField(min_length=1)
    valorCentavos: int = InputField(gt=0, strict=True)
    meioPagamentoId: str = InputField(min_length=1)


def output(row):
    return {"pagamentoId": row.id, "sagaId": row.sagaId, "status": row.status,
            "valorCentavos": row.valorCentavos, "motivo": row.motivo}


async def publish_batch(exchange):
    # O lock só termina após publisher confirm; crash antes do commit causa duplicata segura.
    with Session(engine) as session, session.begin():
        rows = session.exec(select(Outbox).where(Outbox.publicado == False)
                            .with_for_update(skip_locked=True).limit(50)).all()
        for row in rows:
            await exchange.publish(aio_pika.Message(
                body=json.dumps(row.payload).encode(), content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT, message_id=row.id,
                correlation_id=row.correlationId), routing_key=row.payload["tipo"],
                mandatory=True, timeout=3)
            row.publicado = True
            session.add(row)


async def relay_connection():
    connection = await connect()
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange, _ = await topology(channel)
        while True:
            await publish_batch(exchange)
            await asyncio.sleep(1)


async def relay():
    await repeat(relay_connection)


app = create_app("ms-pagamentos", (relay,))


@app.post("/v1/pagamentos", status_code=202)
def processar(body: PagamentoIn, request: Request):
    with Session(engine) as session, session.begin():
        lock(session, "pagamento:" + body.sagaId)
        existing = session.exec(select(Pagamento).where(Pagamento.sagaId == body.sagaId)).first()
        if existing:
            if any(getattr(existing, key) != value for key, value in body.model_dump().items()):
                raise HTTPException(409, "sagaId reutilizado com outro pagamento")
            return output(existing)
        refused = body.meioPagamentoId == "pm_tok_recusado" or body.valorCentavos > 500000
        row = Pagamento(id=uid("pag"), **body.model_dump(),
                        status="RECUSADO" if refused else "APROVADO",
                        motivo="Pagamento não autorizado (simulação)" if refused else None)
        event_id = uid("evt")
        event = {"eventId": event_id, "tipo": "PagamentoRecusado" if refused else "PagamentoAprovado",
                 "versaoAgregado": 1, "ocorridoEm": now().isoformat(),
                 "dados": {**output(row), "solicitacaoId": row.solicitacaoId}}
        session.add(row)
        session.add(Outbox(id=event_id, payload=event, correlationId=request.state.correlation_id))
        return output(row)


@app.get("/v1/pagamentos/por-saga/{saga_id}")
def consultar(saga_id: str):
    with Session(engine) as session:
        row = session.exec(select(Pagamento).where(Pagamento.sagaId == saga_id)).first()
        if not row:
            raise HTTPException(404, "Pagamento não encontrado")
        return output(row)


@app.post("/v1/pagamentos/{pagamento_id}/estorno")
def estornar(pagamento_id: str):
    """Provedor financeiro simulado; estorno idempotente, conciliado por HTTP."""
    with Session(engine) as session, session.begin():
        row = require(session, Pagamento, pagamento_id)
        lock(session, "pagamento:" + row.sagaId)
        session.refresh(row)
        if row.status == "APROVADO":
            row.status = "ESTORNADO"
            session.add(row)
        return output(row)


@app.get("/v1/repasses")
def repasses(solicitacao_id: str):
    with Session(engine) as session:
        rows = session.exec(select(Pagamento).where(Pagamento.solicitacaoId == solicitacao_id,
                                                   Pagamento.status == "APROVADO")).all()
        return {"items": [{"moeda": "BRL", "valor_bruto_centavos": row.valorCentavos,
                           "taxa_plataforma_percentual": 10,
                           "taxa_plataforma_centavos": row.valorCentavos // 10,
                           "valor_liquido_centavos": row.valorCentavos - row.valorCentavos // 10,
                           "previsao_repasse": None} for row in rows]}
