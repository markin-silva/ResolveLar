"""orquestrador-saga — coordena a contratação (aprovação de orçamento) entre os microsserviços.

Não é um microsserviço de domínio: não tem pedidos, orçamentos, reservas nem pagamentos. Fica fora dos
serviços, logo depois do gateway (Kong -> orquestrador), e só comanda os participantes:

    ms-solicitacoes  iniciar / confirmar / cancelar a contratação do orçamento
    ms-agendamentos  reservar / confirmar / liberar o horário
    ms-pagamentos    cobrar / estornar (resultado chega pelo evento da outbox, via RabbitMQ)

O estado de cada SAGA fica no banco próprio (db-orquestrador), para retomar depois de um reinício.
"""
import hashlib
import json
import time
from datetime import timedelta, timezone

import httpx
from fastapi import Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import Session, select

from app import participantes as p
from app.core import create_app, engine, identity, lock, now, require, uid
from app.models import Saga
from app.worker import ESPERA_INICIO_SEGUNDOS, consume, orchestrate

app = create_app("orquestrador-saga", (orchestrate, consume))

GW = "/v1/contratante"  # rota pública no Kong: o link de acompanhamento já aponta para o gateway


class AprovacaoIn(BaseModel):
    horarioEscolhido: AwareDatetime
    meioPagamentoId: str = Field(min_length=1)


def accepted(saga):
    return {"sagaId": saga.id, "solicitacaoId": saga.solicitacaoId, "orcamentoId": saga.orcamentoId,
            "status": "EM_CONFIRMACAO", "_links": {
                "acompanhar": {"href": f"{GW}/solicitacoes/{saga.solicitacaoId}", "method": "GET"}}}


def replay(saga):
    """Mesma Idempotency-Key e mesmo corpo: devolve o resultado da primeira tentativa."""
    if saga.status == "REJEITADA":
        raise HTTPException(saga.erroStatus or 409, saga.motivo or "Aprovação rejeitada")
    if saga.etapa in ("INICIAR", "ABORTAR") or saga.status == "ABORTADA":
        raise HTTPException(503, "A contratação não pôde ser iniciada; tente novamente.")
    return accepted(saga)


def atualizar(saga_id, **campos):
    with Session(engine) as session, session.begin():
        saga = session.exec(select(Saga).where(Saga.id == saga_id).with_for_update()).one()
        if saga.etapa != "INICIAR":
            return None  # o worker já abortou esta SAGA (requisição demorou demais)
        for nome, valor in campos.items():
            setattr(saga, nome, valor)
        session.add(saga)
        session.flush()
        session.expunge(saga)
        return saga


@app.post("/v1/orcamentos/{orcamento_id}/aprovacao", status_code=202)
def aprovar(orcamento_id: str, body: AprovacaoIn, request: Request,
            idempotency_key: str = Header(min_length=1, max_length=200)):
    user = identity(request, "contratante")
    key = hashlib.sha256(f"{user}:{idempotency_key}".encode()).hexdigest()
    normalized = body.model_dump(mode="json")
    normalized["horarioEscolhido"] = body.horarioEscolhido.astimezone(timezone.utc).isoformat()
    fingerprint = hashlib.sha256(json.dumps([orcamento_id, normalized], sort_keys=True).encode()).hexdigest()

    # 1) Registra a SAGA antes de qualquer efeito (idempotência + retomada).
    with Session(engine) as session, session.begin():
        lock(session, "idempotency:" + key)
        previous = session.exec(select(Saga).where(Saga.idempotencyKey == key)).first()
        if previous:
            if previous.fingerprint != fingerprint:
                raise HTTPException(409, "Idempotency-Key reutilizada com outro conteúdo")
            return replay(previous)
        if body.horarioEscolhido <= now():
            raise HTTPException(422, "Escolha um horário futuro")
        saga = Saga(id=uid("saga"), idempotencyKey=key, fingerprint=fingerprint, contratanteId=user,
                    orcamentoId=orcamento_id, inicio=normalized["horarioEscolhido"],
                    meioPagamentoId=body.meioPagamentoId, correlationId=request.state.correlation_id,
                    proximaTentativa=time.time() + ESPERA_INICIO_SEGUNDOS)
        session.add(saga)
        saga_id = saga.id

    # 2) Primeiro passo, síncrono: o ms-solicitacoes valida dono/orçamento e trava a solicitação.
    #    Assim erros de negócio (403, 404, 409) voltam na hora para o cliente.
    falha = None
    try:
        with p.client(request.state.correlation_id, {"X-User-Id": user, "X-User-Role": "contratante"}) as c:
            dados = p.call(c, "POST", p.SOLICITACOES, f"/v1/orcamentos/{orcamento_id}/contratacao",
                           {"sagaId": saga_id})
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status < 500:
            motivo = p.detail(exc) or "Aprovação rejeitada"
            atualizar(saga_id, status="REJEITADA", etapa="FINALIZADA", erroStatus=status, motivo=motivo)
            raise HTTPException(status, motivo)
        falha = exc
    except httpx.HTTPError as exc:
        falha = exc
    if falha is None:
        inicio = body.horarioEscolhido.astimezone(timezone.utc)
        saga = atualizar(saga_id, solicitacaoId=dados["solicitacaoId"], prestadorId=dados["prestadorId"],
                         valorCentavos=dados["valorCentavos"],
                         fim=(inicio + timedelta(minutes=dados["duracaoMinutos"])).isoformat(),
                         etapa="RESERVAR", proximaTentativa=0)
        if saga is not None:
            return accepted(saga)

    # 3) Falha técnica (timeout, 5xx): não se sabe se a solicitação foi travada. O worker desfaz (ABORTAR).
    atualizar(saga_id, status="COMPENSACAO_PENDENTE", etapa="ABORTAR", proximaTentativa=0,
              motivo="Serviço de solicitações indisponível; tente novamente")
    raise HTTPException(503, "Não foi possível iniciar a contratação agora; tente novamente.")


@app.get("/v1/sagas/{saga_id}")
def consultar(saga_id: str, request: Request):
    """Andamento de uma SAGA (usado pelo BFF para mostrar a etapa ao contratante)."""
    user = identity(request)
    with Session(engine) as session:
        saga = require(session, Saga, saga_id)
        if user != saga.contratanteId:
            raise HTTPException(403, "SAGA pertence a outro contratante")
        return {"sagaId": saga.id, "status": saga.status, "etapa": saga.etapa,
                "solicitacaoId": saga.solicitacaoId, "orcamentoId": saga.orcamentoId,
                "reservaId": saga.reservaId, "pagamentoId": saga.pagamentoId, "motivo": saga.motivo}
