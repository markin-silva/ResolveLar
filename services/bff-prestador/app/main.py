import asyncio
from datetime import datetime

from fastapi import Depends, Request
from pydantic import BaseModel, Field

from app import mock_data
from app.config import get_settings
from app.core import ApiError, User, as_first, create_app, current_user, forward_write, new_client, pick, unwrap, upstream_headers

settings = get_settings()
app = create_app("BFF Prestador")

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
