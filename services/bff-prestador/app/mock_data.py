"""Respostas de exemplo dos microsserviços (ENABLE_UPSTREAM_MOCK=true).

Valores de docs/02 (seção 2.6). O prestador do mock é sempre o usuário autenticado,
para a demonstração funcionar com qualquer token de prestador.
"""


def solicitacao(tarefa_id: str, prestador_id: str) -> dict:
    return {
        "id": tarefa_id, "prestadorId": prestador_id, "categoria": "eletricista", "status": "AGENDADA",
        "descricao": "Chuveiro parou de esquentar após queda de energia. Modelo Lorenzetti Advanced 220V, 7500W.",
        "detalhesTecnicos": {
            "tensao": "220V", "potencia_w": 7500,
            "materiais_sugeridos": ["Resistência 7500W 220V", "Fita isolante"],
            "fotos_problema": ["https://cdn.resolvelar.com.br/s/sol_8f21-1.jpg"],
        },
        "local": {"endereco": "Rua das Flores, 120, apto 302", "bairro": "Centro", "cidade": "Lavras",
                  "referencia": "Portão azul, interfone 302"},
        "cliente": {"nome": "Mariana", "telefone": "+55 35 99999-0000"},
    }


def agendamento() -> dict:
    return {"items": [{"reservaId": "res_9", "status": "CONFIRMADA",
                       "inicio": "2026-10-22T17:00:00Z", "fim": "2026-10-22T19:00:00Z"}]}


def repasse() -> dict:
    return {"items": [{
        "moeda": "BRL", "valor_bruto_centavos": 18000, "taxa_plataforma_percentual": 12.0,
        "taxa_plataforma_centavos": 2160, "valor_liquido_centavos": 15840, "previsao_repasse": "2026-10-24",
    }]}


def orcamento_criado(solicitacao_id: str) -> dict:
    return {"id": "orc_42", "solicitacaoId": solicitacao_id, "status": "PENDENTE"}
