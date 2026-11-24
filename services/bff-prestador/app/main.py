import asyncio
from datetime import datetime

from fastapi import Depends, Request
from pydantic import BaseModel, Field

from app import mock_data
from app.config import get_settings
from app.core import ApiError, User, as_first, create_app, current_user, forward_write, new_client, pick, unwrap, upstream_headers

settings = get_settings()
app = create_app("BFF Prestador")

GW = "/v1/prestador"  # prefixo público (Kong): os links devolvidos ao cliente já apontam para o gateway
STATUS_DEMANDA = {
    "AGUARDANDO_ACEITE": "Aberta para orçamentos",
    "EM_CONFIRMACAO": "Confirmando",
    "CONFIRMADA": "Confirmada",
    "CONCLUIDA": "Concluída",
}

# Endereço exato e contato do cliente só são liberados depois do agendamento confirmado (docs/02)
STATUS_LIBERA_CONTATO = {"AGENDADA", "CONFIRMADA", "EM_EXECUCAO", "CONCLUIDA"}


class Valor(BaseModel):
    centavos: int = Field(gt=0)
    moeda: str = "BRL"


class OrcamentoIn(BaseModel):
    valor: Valor
    descricaoServico: str = Field(min_length=3)
    prazoEstimadoDias: int = Field(gt=0)
    validoAte: datetime | None = None


@app.get("/tarefas/{tarefa_id}")
async def detalhe_tarefa(tarefa_id: str, request: Request, user: User = Depends(current_user)):
    """Detalhe técnico + decomposição financeira (docs/02, seção 2.6).

    Consulta 3 microsserviços em paralelo. Só a solicitação é essencial: se agendamento ou
    pagamentos falharem (ENABLE_UPSTREAM_MOCK=false), o bloco correspondente é omitido.
    """
    headers = upstream_headers(request, user)
    params = {"solicitacao_id": tarefa_id}
    async with new_client() as client:
        sol_r, ag_r, rep_r = await asyncio.gather(
            client.get(f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes/{tarefa_id}", headers=headers),
            client.get(f"{settings.MS_AGENDAMENTOS_URL}/v1/agendamentos", params=params, headers=headers),
            client.get(f"{settings.MS_PAGAMENTOS_URL}/v1/repasses", params=params, headers=headers),
            return_exceptions=True)

    sol = unwrap(request, sol_r, lambda: mock_data.solicitacao(tarefa_id, user.id))
    # autorização fina: o prestador só vê tarefas que são dele (o Kong só valida o perfil)
    if pick(sol, "prestadorId", "prestador_id") != user.id:
        raise ApiError(403, "Forbidden", "Esta tarefa não está atribuída a você.")

    agendamento = as_first(unwrap(request, ag_r, mock_data.agendamento, essential=False))
    repasse = as_first(unwrap(request, rep_r, mock_data.repasse, essential=False))

    status = pick(sol, "status", default="DESCONHECIDO")
    out = {
        "tarefa_id": tarefa_id,
        "categoria": sol.get("categoria"),
        "status": status,
        "descricao": sol.get("descricao"),
        "detalhes_tecnicos": pick(sol, "detalhesTecnicos", "detalhes_tecnicos", default={}),
    }
    if agendamento:
        out["agendamento"] = {"inicio": agendamento.get("inicio"), "fim": agendamento.get("fim")}
    if status in STATUS_LIBERA_CONTATO:
        out["local"] = sol.get("local")
        out["cliente"] = sol.get("cliente")
    if repasse:
        # bruto, taxa e líquido são calculados pelo MS Pagamentos: o BFF só repassa (sem regra financeira aqui)
        out["financeiro"] = {k: repasse.get(k) for k in (
            "moeda", "valor_bruto_centavos", "taxa_plataforma_percentual", "taxa_plataforma_centavos",
            "valor_liquido_centavos", "previsao_repasse")}
    return out


@app.post("/solicitacoes/{solicitacao_id}/orcamentos")
async def enviar_orcamento(solicitacao_id: str, body: OrcamentoIn, request: Request,
                           user: User = Depends(current_user)):
    return await forward_write(
        request, "POST", f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes/{solicitacao_id}/orcamentos", user,
        body.model_dump(mode="json", exclude_none=True),
        mock_status=201, mock_body=mock_data.orcamento_criado(solicitacao_id))


# --------------------------------------------------------------------------- fila e visões do prestador
def resumo_demanda(sol: dict) -> dict:
    """Demanda como o prestador vê ANTES de ser escolhido: sem endereço completo, nome ou contato (docs/02)."""
    sid = pick(sol, "id", "solicitacao_id")
    status = pick(sol, "status", default="AGUARDANDO_ACEITE")
    return {
        "solicitacao_id": sid,
        "categoria": sol.get("categoria"),
        "descricao": sol.get("descricao"),
        "cidade": sol.get("cidade"),
        "uf": sol.get("uf"),
        "bairro": sol.get("bairro"),
        "status_codigo": status,
        "status": STATUS_DEMANDA.get(status, status),
        "_links": {
            "self": {"href": f"{GW}/solicitacoes/{sid}", "method": "GET"},
            **({"enviarOrcamento": {"href": f"{GW}/solicitacoes/{sid}/orcamentos", "method": "POST"}}
               if status == "AGUARDANDO_ACEITE" else {}),
        },
    }


async def perfil_do_prestador(client, request: Request, user: User) -> dict:
    """Categorias e cidade do prestador logado, lidas do Read DB do CQRS (ms-prestadores)."""
    r = await client.get(f"{settings.MS_PRESTADORES_URL}/v1/prestadores/{user.id}",
                         headers=upstream_headers(request, user))
    if r.status_code == 404:
        raise ApiError(409, "Conflict", "Seu perfil de profissional ainda não foi publicado. Tente em instantes.")
    r.raise_for_status()
    return r.json()


@app.get("/solicitacoes")
async def fila_de_demandas(request: Request, categoria: str | None = None, cidade: str | None = None,
                           page: int = 1, size: int = 20, user: User = Depends(current_user)):
    """Fila de demandas abertas. Sem filtros, usa as categorias e a cidade do perfil do prestador."""
    headers = upstream_headers(request, user)
    async with new_client() as client:
        try:
            perfil = await perfil_do_prestador(client, request, user)
        except ApiError:
            if not (categoria or cidade):
                raise
            perfil = {}
        except Exception:
            raise ApiError(503, "Service Unavailable", "Não foi possível ler seu perfil agora.")
        categorias = [categoria] if categoria else (perfil.get("categorias") or [])
        cidade_alvo = cidade or perfil.get("cidade")
        params = {"status": "AGUARDANDO_ACEITE", "page": page, "size": size,
                  **({"cidade": cidade_alvo} if cidade_alvo else {})}
        resultados = await asyncio.gather(
            *[client.get(f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes", params={**params, "categoria": c},
                         headers=headers) for c in categorias], return_exceptions=True)
    itens: dict[str, dict] = {}
    for res in resultados:
        data = unwrap(request, res, {"items": []})
        for sol in (data or {}).get("items", []):
            itens[pick(sol, "id")] = sol
    ordenadas = sorted(itens.values(), key=lambda x: pick(x, "id", default=""), reverse=True)
    return {
        "items": [resumo_demanda(x) for x in ordenadas],
        "page": page, "size": size,
        "filtros": {"categorias": categorias, "cidade": cidade_alvo},
    }


@app.get("/solicitacoes/{solicitacao_id}")
async def detalhe_da_demanda(solicitacao_id: str, request: Request, user: User = Depends(current_user)):
    """Demanda aberta (visão pública) ou, se o prestador foi escolhido, o detalhe completo da tarefa."""
    async with new_client() as client:
        (res,) = await asyncio.gather(
            client.get(f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes/{solicitacao_id}",
                       headers=upstream_headers(request, user)), return_exceptions=True)
    sol = unwrap(request, res, lambda: mock_data.solicitacao(solicitacao_id, user.id))
    if pick(sol, "prestadorId", "prestador_id") == user.id:
        return await detalhe_tarefa(solicitacao_id, request, user)  # escolhido: detalhe completo
    return resumo_demanda(sol)


@app.get("/orcamentos")
async def meus_orcamentos(request: Request, status: str | None = None, user: User = Depends(current_user)):
    """Orçamentos que o prestador enviou, com o estado de cada solicitação."""
    headers = upstream_headers(request, user)
    params = {"prestador_id": user.id, **({"status": status} if status else {})}
    async with new_client() as client:
        (res,) = await asyncio.gather(
            client.get(f"{settings.MS_SOLICITACOES_URL}/v1/orcamentos", params=params, headers=headers),
            return_exceptions=True)
    data = unwrap(request, res, {"items": []})
    out = []
    for o in (data or {}).get("items", []):
        valor = o.get("valor") or {"centavos": 0, "moeda": "BRL"}
        out.append({
            "orcamento_id": pick(o, "id"), "solicitacao_id": pick(o, "solicitacaoId"), "status": o.get("status"),
            "valor": {"centavos": valor["centavos"], "moeda": valor.get("moeda", "BRL")},
            "prazoEstimadoDias": o.get("prazoEstimadoDias"), "descricaoServico": o.get("descricaoServico"),
            "_links": {"solicitacao": {"href": f"{GW}/solicitacoes/{pick(o, 'solicitacaoId')}", "method": "GET"}},
        })
    return {"items": out}


@app.get("/agenda")
async def minha_agenda(request: Request, de: str | None = None, ate: str | None = None,
                       user: User = Depends(current_user)):
    """Reservas do prestador (agenda), da mais próxima para a mais distante."""
    params = {"prestador_id": user.id, **({"de": de} if de else {}), **({"ate": ate} if ate else {})}
    async with new_client() as client:
        (res,) = await asyncio.gather(
            client.get(f"{settings.MS_AGENDAMENTOS_URL}/v1/agendamentos", params=params,
                       headers=upstream_headers(request, user)), return_exceptions=True)
    data = unwrap(request, res, {"items": []})
    return {"items": [{
        "reserva_id": pick(r, "reservaId", "id"), "solicitacao_id": r.get("solicitacaoId"),
        "inicio": r.get("inicio"), "fim": r.get("fim"), "status": r.get("status"),
        "_links": {"solicitacao": {"href": f"{GW}/solicitacoes/{r.get('solicitacaoId')}", "method": "GET"}},
    } for r in (data or {}).get("items", [])]}


@app.get("/ganhos")
async def meus_ganhos(request: Request, user: User = Depends(current_user)):
    """Extrato: bruto, taxa e líquido de cada serviço confirmado. Os valores vêm do ms-pagamentos
    (o BFF só soma); soma em centavos, sem conversão de escala."""
    headers = upstream_headers(request, user)
    async with new_client() as client:
        (res,) = await asyncio.gather(
            client.get(f"{settings.MS_SOLICITACOES_URL}/v1/solicitacoes", params={"status": "CONFIRMADA", "size": 50},
                       headers=headers), return_exceptions=True)
        data = unwrap(request, res, {"items": []})
        minhas = [x for x in (data or {}).get("items", []) if pick(x, "prestadorId") == user.id]
        reps = await asyncio.gather(
            *[client.get(f"{settings.MS_PAGAMENTOS_URL}/v1/repasses", params={"solicitacao_id": pick(x, "id")},
                         headers=headers) for x in minhas], return_exceptions=True)
    itens = []
    for sol, rep_r in zip(minhas, reps):
        rep = as_first(unwrap(request, rep_r, None, essential=False))
        if not rep:
            continue
        itens.append({"solicitacao_id": pick(sol, "id"), "categoria": sol.get("categoria"),
                      **{k: rep.get(k) for k in ("valor_bruto_centavos", "taxa_plataforma_centavos",
                                                  "valor_liquido_centavos", "previsao_repasse")}})
    soma = lambda k: sum(int(i.get(k) or 0) for i in itens)  # noqa: E731
    return {
        "moeda": "BRL", "items": itens,
        "totais": {"valor_bruto_centavos": soma("valor_bruto_centavos"),
                   "taxa_plataforma_centavos": soma("taxa_plataforma_centavos"),
                   "valor_liquido_centavos": soma("valor_liquido_centavos")},
    }

