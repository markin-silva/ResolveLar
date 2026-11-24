import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import Session, select

from app.core import create_app, engine, identity, lock, now, require, uid
from app.models import Orcamento, Saga, Solicitacao
from app.worker import consume, orchestrate

app = create_app("ms-solicitacoes", (orchestrate, consume))


class Endereco(BaseModel):
    cep: str
    cidade: str
    uf: str = Field(min_length=2, max_length=2)
    bairro: str | None = None
    logradouro: str | None = None  # só liberado ao prestador depois da confirmação


class SolicitacaoIn(BaseModel):
    categoria: str = Field(min_length=1)
    descricao: str = Field(min_length=5)
    endereco: Endereco
    janelaPreferida: AwareDatetime | None = None


class Valor(BaseModel):
    centavos: int = Field(gt=0, strict=True)
    moeda: str = Field(default="BRL", pattern="^BRL$")


class OrcamentoIn(BaseModel):
    valor: Valor
    descricaoServico: str = Field(min_length=3)
    prazoEstimadoDias: int = Field(gt=0)
    duracaoMinutos: int = Field(default=60, gt=0, le=1440)
    validoAte: AwareDatetime | None = None


class AprovacaoIn(BaseModel):
    horarioEscolhido: AwareDatetime
    meioPagamentoId: str = Field(min_length=1)


def link(path, method="GET"):
    return {"href": "/v1/" + path, "method": method}


def view_quote(row):
    status = row.status
    if status == "PENDENTE" and datetime.fromisoformat(row.validoAte) <= now():
        status = "EXPIRADO"
    links = {"self": link("orcamentos/" + row.id),
             "solicitacao": link("solicitacoes/" + row.solicitacaoId)}
    if status == "PENDENTE":
        links.update(aprovar=link(f"orcamentos/{row.id}/aprovacao", "POST"),
                     recusar=link(f"orcamentos/{row.id}/recusa", "POST"))
    return {"id": row.id, "solicitacaoId": row.solicitacaoId, "status": status,
            "valor": {"centavos": row.valorCentavos, "moeda": "BRL"},
            "prestador": {"id": row.prestadorId}, "descricaoServico": row.descricaoServico,
            "prazoEstimadoDias": row.prazoEstimadoDias, "duracaoMinutos": row.duracaoMinutos,
            "validoAte": row.validoAte, "_links": links}


def owner(sol, request):
    if identity(request, "contratante") != sol.contratanteId:
        raise HTTPException(403, "Solicitação pertence a outro contratante")


def accepted(saga):
    return {"sagaId": saga.id, "solicitacaoId": saga.solicitacaoId, "orcamentoId": saga.orcamentoId,
            "status": "EM_CONFIRMACAO", "_links": {
                "acompanhar": link("solicitacoes/" + saga.solicitacaoId)}}


@app.post("/v1/solicitacoes", status_code=201)
def criar(body: SolicitacaoIn, request: Request):
    row = Solicitacao(id=uid("sol"), contratanteId=identity(request, "contratante"),
                      categoria=body.categoria, descricao=body.descricao,
                      local=body.endereco.model_dump())
    with Session(engine) as session, session.begin():
        session.add(row)
        return {**row.model_dump(), "_links": {"self": link("solicitacoes/" + row.id)}}


def resumo(sol, *, publico: bool):
    """Resumo para listas. `publico=True` é a visão da fila do prestador: sem endereço completo,
    sem contratante e sem contato (docs/02 libera isso só depois da confirmação)."""
    local = sol.local or {}
    out = {"id": sol.id, "categoria": sol.categoria, "descricao": sol.descricao, "status": sol.status,
           "cidade": local.get("cidade"), "uf": local.get("uf"), "bairro": local.get("bairro"),
           "_links": {"self": link("solicitacoes/" + sol.id)}}
    if not publico:
        out.update({"contratanteId": sol.contratanteId, "prestadorId": sol.prestadorId, "motivo": sol.motivo,
                    "local": local})
    return out


@app.get("/v1/solicitacoes")
def listar_solicitacoes(request: Request, status: str | None = None, categoria: str | None = None,
                        cidade: str | None = None, page: int = 1, size: int = 20):
    """Contratante: os pedidos dele. Prestador: a fila de demandas abertas (categoria/cidade, visão resumida)
    e as solicitações em que ele foi escolhido."""
    user = identity(request)
    role = request.headers.get("X-User-Role")
    page, size = max(page, 1), min(max(size, 1), 50)
    with Session(engine) as session:
        if role == "contratante":
            stmt = select(Solicitacao).where(Solicitacao.contratanteId == user)
            publico = False
        elif role == "prestador":
            stmt = select(Solicitacao).where(
                (Solicitacao.prestadorId == user) | (Solicitacao.status == "AGUARDANDO_ACEITE"))
            publico = True
        else:
            raise HTTPException(403, "Perfil não autorizado")
        if status:
            stmt = stmt.where(Solicitacao.status == status.upper())
        if categoria:
            stmt = stmt.where(Solicitacao.categoria == categoria.lower())
        rows = session.exec(stmt.order_by(Solicitacao.id.desc())).all()
        if cidade:  # a cidade fica dentro do JSON `local`; filtra em memória (volume de MVP)
            rows = [r for r in rows if (r.local or {}).get("cidade", "").lower() == cidade.lower()]
        total = len(rows)
        page_rows = rows[(page - 1) * size: page * size]
        # prestador escolhido (dono) vê o resumo normal; os demais, a visão pública
        items = [resumo(r, publico=publico and r.prestadorId != user) for r in page_rows]
        return {"items": items, "page": page, "size": size, "total": total}


@app.get("/v1/orcamentos")
def listar_orcamentos(request: Request, prestador_id: str, status: str | None = None):
    """Orçamentos enviados por um prestador (só os dele)."""
    if identity(request, "prestador") != prestador_id:
        raise HTTPException(403, "Só é possível consultar os próprios orçamentos")
    with Session(engine) as session:
        stmt = select(Orcamento).where(Orcamento.prestadorId == prestador_id)
        if status:
            stmt = stmt.where(Orcamento.status == status.upper())
        rows = session.exec(stmt.order_by(Orcamento.id.desc())).all()
        return {"items": [view_quote(r) for r in rows]}


@app.get("/v1/solicitacoes/{solicitacao_id}")
def consultar(solicitacao_id: str, request: Request):
    user = identity(request)
    with Session(engine) as session:
        sol = require(session, Solicitacao, solicitacao_id)
        if user not in (sol.contratanteId, sol.prestadorId):
            if request.headers.get("X-User-Role") == "prestador" and sol.status == "AGUARDANDO_ACEITE":
                return resumo(sol, publico=True)  # demanda aberta: visão sem endereço/contato
            raise HTTPException(403, "Recurso não pertence ao usuário")
        result = sol.model_dump()
        if sol.sagaId:
            saga = require(session, Saga, sol.sagaId)
            result["saga"] = {"sagaId": saga.id, "status": saga.status, "etapa": saga.etapa,
                              "reservaId": saga.reservaId, "pagamentoId": saga.pagamentoId,
                              "motivo": saga.motivo}
        result["_links"] = {"self": link("solicitacoes/" + sol.id),
                            "orcamentos": link(f"solicitacoes/{sol.id}/orcamentos")}
        return result


@app.post("/v1/solicitacoes/{solicitacao_id}/orcamentos", status_code=201)
def propor(solicitacao_id: str, body: OrcamentoIn, request: Request):
    prestador = identity(request, "prestador")
    expires = body.validoAte or now() + timedelta(days=7)
    if expires <= now():
        raise HTTPException(422, "Validade deve estar no futuro")
    with Session(engine) as session, session.begin():
        lock(session, "sol:" + solicitacao_id)
        sol = require(session, Solicitacao, solicitacao_id)
        if sol.status != "AGUARDANDO_ACEITE":
            raise HTTPException(409, "Solicitação não aceita novos orçamentos")
        row = Orcamento(id=uid("orc"), solicitacaoId=sol.id, prestadorId=prestador,
                        valorCentavos=body.valor.centavos, descricaoServico=body.descricaoServico,
                        prazoEstimadoDias=body.prazoEstimadoDias, duracaoMinutos=body.duracaoMinutos,
                        validoAte=expires.isoformat())
        session.add(row)
        return view_quote(row)


@app.get("/v1/solicitacoes/{solicitacao_id}/orcamentos")
def listar(solicitacao_id: str, request: Request):
    with Session(engine) as session:
        owner(require(session, Solicitacao, solicitacao_id), request)
        rows = session.exec(select(Orcamento).where(Orcamento.solicitacaoId == solicitacao_id)).all()
        return {"items": [view_quote(row) for row in rows]}


@app.get("/v1/orcamentos/{orcamento_id}")
def consultar_orcamento(orcamento_id: str, request: Request):
    with Session(engine) as session:
        row = require(session, Orcamento, orcamento_id)
        sol = require(session, Solicitacao, row.solicitacaoId)
        if identity(request) not in (sol.contratanteId, row.prestadorId):
            raise HTTPException(403, "Recurso não pertence ao usuário")
        return view_quote(row)


@app.post("/v1/orcamentos/{orcamento_id}/recusa")
def recusar(orcamento_id: str, request: Request):
    with Session(engine) as session, session.begin():
        row = require(session, Orcamento, orcamento_id)
        lock(session, "sol:" + row.solicitacaoId)
        session.refresh(row)
        owner(require(session, Solicitacao, row.solicitacaoId), request)
        if row.status not in ("PENDENTE", "RECUSADO"):
            raise HTTPException(409, "Orçamento não pode ser recusado")
        row.status = "RECUSADO"
        session.add(row)
        return view_quote(row)


@app.post("/v1/orcamentos/{orcamento_id}/aprovacao", status_code=202)
def aprovar(orcamento_id: str, body: AprovacaoIn, request: Request,
            idempotency_key: str = Header(min_length=1, max_length=200)):
    user = identity(request, "contratante")
    key = hashlib.sha256(f"{user}:{idempotency_key}".encode()).hexdigest()
    normalized = body.model_dump(mode="json")
    normalized["horarioEscolhido"] = body.horarioEscolhido.astimezone(timezone.utc).isoformat()
    fingerprint = hashlib.sha256(json.dumps([orcamento_id, normalized], sort_keys=True).encode()).hexdigest()
    with Session(engine) as session, session.begin():
        lock(session, "idempotency:" + key)
        previous = session.exec(select(Saga).where(Saga.idempotencyKey == key)).first()
        if previous:
            if previous.fingerprint != fingerprint:
                raise HTTPException(409, "Idempotency-Key reutilizada com outro conteúdo")
            return accepted(previous)
        quote = require(session, Orcamento, orcamento_id)
        lock(session, "sol:" + quote.solicitacaoId)
        session.refresh(quote)
        sol = require(session, Solicitacao, quote.solicitacaoId)
        owner(sol, request)
        if (quote.status != "PENDENTE" or datetime.fromisoformat(quote.validoAte) <= now()
                or sol.status != "AGUARDANDO_ACEITE"):
            raise HTTPException(409, "Orçamento vencido, recusado ou consumido")
        if body.horarioEscolhido <= now():
            raise HTTPException(422, "Escolha um horário futuro")
        saga = Saga(id=uid("saga"), idempotencyKey=key, fingerprint=fingerprint,
                    solicitacaoId=sol.id, orcamentoId=quote.id, prestadorId=quote.prestadorId,
                    valorCentavos=quote.valorCentavos, inicio=normalized["horarioEscolhido"],
                    fim=(body.horarioEscolhido + timedelta(minutes=quote.duracaoMinutos)).isoformat(),
                    meioPagamentoId=body.meioPagamentoId, correlationId=request.state.correlation_id)
        sol.status, sol.sagaId, sol.motivo = "EM_CONFIRMACAO", saga.id, None
        quote.status = "EM_CONFIRMACAO"
        session.add_all([saga, sol, quote])
        return accepted(saga)
