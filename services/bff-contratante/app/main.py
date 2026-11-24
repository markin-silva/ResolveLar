import asyncio
from datetime import datetime

from fastapi import Depends, Header, Request
from pydantic import BaseModel, Field

from app import mock_data
from app.config import get_settings
from app.core import (ApiError, User, as_list, brl, create_app, current_user, forward_write, new_client, pick,
                      unwrap, upstream_headers)

settings = get_settings()
app = create_app("BFF Contratante")

# Status técnico -> texto para a tela (docs/02, seção 2.5)
STATUS_LEGIVEL = {
    "ABERTA": "Aguardando sua escolha",
    "AGUARDANDO_ACEITE": "Aguardando sua escolha",
    "EM_CONFIRMACAO": "Confirmando seu agendamento",
    "CONFIRMADA": "Serviço confirmado",
    "CONCLUIDA": "Serviço concluído",
}


GW = "/v1/contratante"  # prefixo público (Kong): os links devolvidos ao cliente já apontam para o gateway


def estado_solicitacao(sol: dict, solicitacao_id: str) -> dict:
    """Estado da solicitação para a tela: código técnico (polling da SAGA), texto, motivo e links."""
    codigo = pick(sol, "status", default="ABERTA")
    saga = sol.get("saga") or {}
    return {
        "solicitacao_id": solicitacao_id,
        "status_codigo": codigo,
        "status": STATUS_LEGIVEL.get(codigo, codigo),
        "motivo": pick(sol, "motivo") or saga.get("motivo"),
        "saga": {"status": saga.get("status"), "etapa": saga.get("etapa")} if saga else None,
        "prestador_id": pick(sol, "prestadorId", "prestador_id"),
        "_links": {"self": {"href": f"{GW}/solicitacoes/{solicitacao_id}", "method": "GET"},
                   "orcamentos": {"href": f"{GW}/solicitacoes/{solicitacao_id}/orcamentos", "method": "GET"}},
    }


def links_orcamento(orc: dict, orcamento_id: str) -> dict:
    """Ações permitidas no orçamento, guiadas pelos `_links` do ms-solicitacoes (HATEOAS).

    Sem `_links` no upstream (mock/legado) assume-se orçamento pendente, que pode ser aprovado ou recusado.
    """
    upstream = orc.get("_links")
    rels = ("aprovar", "recusar") if upstream is None else tuple(r for r in ("aprovar", "recusar") if r in upstream)
    destinos = {"aprovar": f"{GW}/orcamentos/{orcamento_id}/aprovacao", "recusar": f"{GW}/orcamentos/{orcamento_id}/recusa"}
    return {r: {"href": destinos[r], "method": "POST"} for r in rels}


class Endereco(BaseModel):
    cep: str
    cidade: str
    uf: str = Field(min_length=2, max_length=2)


class SolicitacaoIn(BaseModel):
    categoria: str
    descricao: str = Field(min_length=5)
    endereco: Endereco
    janelaPreferida: datetime | None = None


class TriagemIn(BaseModel):
    descricao: str = Field(min_length=10, max_length=2000)
    cidade: str | None = None
    uf: str | None = Field(default=None, min_length=2, max_length=2)


class AvaliacaoIn(BaseModel):
    prestadorId: str
    nota: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


class AprovacaoIn(BaseModel):
    horarioEscolhido: datetime
    meioPagamentoId: str  # token do meio de pagamento, nunca dados de cartão


def resumo_prestador(p: dict) -> dict:
    """Só o necessário para exibir: sem contato, sem preço interno."""
    return {
        "prestador_id": pick(p, "prestadorId", "id"),
        "nome": p.get("nome"),
        "foto_url": pick(p, "fotoUrl", "foto_url"),
        "categorias": p.get("categorias", []),
        "cidade": p.get("cidade"),
        "nota": pick(p, "notaMedia", "nota"),
        "servicos_realizados": pick(p, "servicosConcluidos", "servicos_realizados", default=0),
        "disponivel_hoje": pick(p, "disponivelHoje", default=False),
    }


# --------------------------------------------------------------------------- rotas
@app.get("/prestadores")
async def buscar_prestadores(request: Request, cidade: str | None = None, categoria: str | None = None,
                             page: int = 1, size: int = 20, user: User = Depends(current_user)):
    params = {k: v for k, v in {"cidade": cidade, "categoria": categoria, "page": page, "size": size}.items()
              if v is not None}
    async with new_client() as client:
        (result,) = await asyncio.gather(
            client.get(f"{settings.MS_PRESTADORES_URL}/v1/prestadores", params=params,
                       headers=upstream_headers(request, user)),
            return_exceptions=True)
    data = unwrap(request, result, mock_data.prestadores_busca)
    return {"items": [resumo_prestador(p) for p in as_list(data)], "page": page, "size": size}


@app.post("/triagem")
async def triagem(body: TriagemIn, request: Request, user: User = Depends(current_user)):
    """Assistente de Triagem IA (ms-triagem): categoria, urgência, orientações e prestadores reais."""
    return await forward_write(
        request, "POST", f"{settings.MS_TRIAGEM_URL}/v1/triagem", user,
        body.model_dump(mode="json", exclude_none=True), timeout=settings.TRIAGEM_TIMEOUT_SECONDS,
        mock_status=200, mock_body=mock_data.triagem())


@app.post("/solicitacoes/{solicitacao_id}/avaliacao")
async def avaliar_servico(solicitacao_id: str, body: AvaliacaoIn, request: Request,
                          user: User = Depends(current_user)):
    """Avaliação do serviço (ms-avaliacoes): 201; 409 se a solicitação já foi avaliada."""
    return await forward_write(
        request, "POST", f"{settings.MS_AVALIACOES_URL}/v1/solicitacoes/{solicitacao_id}/avaliacao", user,
        body.model_dump(mode="json", exclude_none=True),
        mock_status=201, mock_body=mock_data.avaliacao_criada(solicitacao_id, body.prestadorId, body.nota))


@app.post("/solicitacoes")
async def criar_solicitacao(body: SolicitacaoIn, request: Request, user: User = Depends(current_user)):
    return await forward_write(
        request, "POST", f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes", user,
        body.model_dump(mode="json", exclude_none=True),
        mock_status=201, mock_body=mock_data.solicitacao_criada())


@app.get("/solicitacoes/{solicitacao_id}/orcamentos")
async def comparar_orcamentos(solicitacao_id: str, request: Request, user: User = Depends(current_user)):
    """Agrega solicitação + orçamentos + reputação dos prestadores (docs/02, seção 2.5)."""
    headers = upstream_headers(request, user)
    base = settings.MS_SOLICITACOES_URL
    async with new_client() as client:
        # 1) solicitação e orçamentos em paralelo
        sol_r, orc_r = await asyncio.gather(
            client.get(f"{base}/v1/solicitacoes/{solicitacao_id}", headers=headers),
            client.get(f"{base}/v1/solicitacoes/{solicitacao_id}/orcamentos", headers=headers),
            return_exceptions=True)
        sol = unwrap(request, sol_r, lambda: mock_data.solicitacao(solicitacao_id, user.id))
        orcamentos = as_list(unwrap(request, orc_r, lambda: mock_data.orcamentos(solicitacao_id)))

        # autorização fina: o Kong só garante o perfil, não o dono do recurso
        dono = pick(sol, "contratanteId", "contratante_id")
        if dono and dono != user.id:
            raise ApiError(403, "Forbidden", "Esta solicitação pertence a outro contratante.")

        pendentes = [o for o in orcamentos if o.get("status", "PENDENTE") == "PENDENTE"]

        # 2) reputação de cada prestador em paralelo; falha parcial = usa os dados embutidos no orçamento
        ids = [pick(o.get("prestador"), "id", "prestadorId") for o in pendentes]
        reps = await asyncio.gather(
            *[client.get(f"{settings.MS_PRESTADORES_URL}/v1/prestadores/{pid}", headers=headers) for pid in ids],
            return_exceptions=True)

    orcamentos_out = []
    for orc, pid, rep_r in zip(pendentes, ids, reps):
        rep = unwrap(request, rep_r, lambda pid=pid: mock_data.PRESTADORES.get(pid), essential=False) or {}
        emb = orc.get("prestador") or {}
        valor = orc.get("valor") or {"centavos": 0, "moeda": "BRL"}
        dias = orc.get("prazoEstimadoDias")
        orcamento_id = pick(orc, "id", "orcamentoId")
        orcamentos_out.append({
            "orcamento_id": orcamento_id,
            "prestador": {
                "prestador_id": pid,
                "nome": pick(rep, "nome") or emb.get("nome"),
                "foto_url": pick(rep, "fotoUrl", "foto_url"),
                "nota": pick(rep, "notaMedia") if rep else emb.get("notaMedia"),
                "servicos_realizados": pick(rep, "servicosConcluidos", default=0),
            },
            "valor": {"centavos": valor["centavos"], "moeda": valor.get("moeda", "BRL")},
            "valor_formatado": brl(valor["centavos"]),
            "prazo": orc.get("prazo") or (f"Em até {dias} dia(s)" if dias else None),
            "_links": links_orcamento(orc, orcamento_id),
        })

    return {
        **estado_solicitacao(sol, solicitacao_id),
        "titulo": pick(sol, "titulo") or (pick(sol, "descricao", default="") or "")[:60] or solicitacao_id,
        "orcamentos": orcamentos_out,
    }


@app.get("/solicitacoes/{solicitacao_id}")
async def estado_da_solicitacao(solicitacao_id: str, request: Request, user: User = Depends(current_user)):
    """Estado atual da solicitação (inclui a SAGA): usado pelo cliente para acompanhar `EM_CONFIRMACAO`."""
    async with new_client() as client:
        (result,) = await asyncio.gather(
            client.get(f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes/{solicitacao_id}",
                       headers=upstream_headers(request, user)),
            return_exceptions=True)
    sol = unwrap(request, result, lambda: mock_data.solicitacao(solicitacao_id, user.id))
    dono = pick(sol, "contratanteId", "contratante_id")
    if dono and dono != user.id:
        raise ApiError(403, "Forbidden", "Esta solicitação pertence a outro contratante.")
    return estado_solicitacao(sol, solicitacao_id)


@app.post("/orcamentos/{orcamento_id}/recusa")
async def recusar_orcamento(orcamento_id: str, request: Request, user: User = Depends(current_user)):
    """Recusa um orçamento pendente (ação do link HATEOAS `recusar`)."""
    return await forward_write(
        request, "POST", f"{settings.MS_SOLICITACOES_URL}/v1/orcamentos/{orcamento_id}/recusa", user, {},
        mock_status=200, mock_body={"id": orcamento_id, "status": "RECUSADO"})


@app.post("/orcamentos/{orcamento_id}/aprovacao")
async def aprovar_orcamento(orcamento_id: str, body: AprovacaoIn, request: Request,
                            user: User = Depends(current_user),
                            idempotency_key: str | None = Header(None)):
    """Inicia a SAGA no ms-solicitacoes (202 Accepted, status EM_CONFIRMACAO)."""
    return await forward_write(
        request, "POST", f"{settings.MS_SOLICITACOES_URL}/v1/orcamentos/{orcamento_id}/aprovacao", user,
        body.model_dump(mode="json"), idempotency_key=idempotency_key,
        mock_status=202, mock_body=mock_data.aprovacao_aceita(orcamento_id))
