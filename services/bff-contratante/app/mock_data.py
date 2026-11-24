"""Respostas de exemplo dos microsserviços (ENABLE_UPSTREAM_MOCK=true).

Seguem os contratos REST de docs/04 (camelCase) e os dados de docs/02 (seção 2.5).
"""

PRESTADORES = {
    "prest_17": {
        "prestadorId": "prest_17", "nome": "Carlos Silva",
        "fotoUrl": "https://cdn.resolvelar.com.br/p/prest_17.jpg",
        "categorias": ["eletricista", "instalador"], "cidade": "Lavras", "uf": "MG",
        "notaMedia": 4.8, "totalAvaliacoes": 132, "servicosConcluidos": 132,
        "disponivelHoje": True, "precoMedioCentavos": 15000, "ativo": True,
    },
    "prest_23": {
        "prestadorId": "prest_23", "nome": "Ana Souza",
        "fotoUrl": "https://cdn.resolvelar.com.br/p/prest_23.jpg",
        "categorias": ["eletricista"], "cidade": "Lavras", "uf": "MG",
        "notaMedia": 4.9, "totalAvaliacoes": 87, "servicosConcluidos": 87,
        "disponivelHoje": True, "precoMedioCentavos": 14000, "ativo": True,
    },
}


def prestadores_busca() -> dict:
    return {"items": list(PRESTADORES.values()), "page": 1, "size": 20, "total": len(PRESTADORES)}


def solicitacao(solicitacao_id: str, contratante_id: str) -> dict:
    return {
        "id": solicitacao_id, "titulo": "Chuveiro queimado", "categoria": "eletricista",
        "status": "ABERTA", "contratanteId": contratante_id,
    }


def orcamentos(solicitacao_id: str) -> dict:
    return {"items": [
        {"id": "orc_42", "solicitacaoId": solicitacao_id, "status": "PENDENTE",
         "valor": {"centavos": 18000, "moeda": "BRL"}, "prazo": "Amanhã, 14h–16h",
         "prestador": {"id": "prest_17", "nome": "Carlos Silva", "notaMedia": 4.8}},
        {"id": "orc_43", "solicitacaoId": solicitacao_id, "status": "PENDENTE",
         "valor": {"centavos": 15000, "moeda": "BRL"}, "prazo": "Hoje, 18h–20h",
         "prestador": {"id": "prest_23", "nome": "Ana Souza", "notaMedia": 4.9}},
    ]}


def solicitacao_criada() -> dict:
    return {"id": "sol_8f21", "status": "ABERTA", "criadaEm": "2026-10-21T15:04:00Z"}


def aprovacao_aceita(orcamento_id: str) -> dict:
    return {
        "sagaId": "saga_52", "solicitacaoId": "sol_8f21", "orcamentoId": orcamento_id,
        "status": "EM_CONFIRMACAO",
        "_links": {"acompanhar": {"href": "/v1/solicitacoes/sol_8f21", "method": "GET"}},
    }


def triagem() -> dict:
    """Formato de POST /v1/triagem do ms-triagem (ver .ai-memory/DECISIONS_LOG.md)."""
    return {
        "triagemId": "tri_mock", "categoria": "eletricista", "urgencia": "MEDIA",
        "resumo": "Chuveiro elétrico não esquenta e o disjuntor desarma.",
        "orientacoesSeguranca": ["Desligue o disjuntor do chuveiro antes de mexer no aparelho.",
                                 "Não troque o disjuntor por um de amperagem maior."],
        "perguntasComplementares": ["Qual a potência do chuveiro?"],
        "prestadoresSugeridos": [
            {"prestadorId": p["prestadorId"], "nome": p["nome"], "categorias": p["categorias"],
             "cidade": p["cidade"], "notaMedia": p["notaMedia"], "totalAvaliacoes": p["totalAvaliacoes"],
             "disponivelHoje": p["disponivelHoje"], "precoMedioCentavos": p["precoMedioCentavos"]}
            for p in PRESTADORES.values()],
        "fontes": [], "modo": "fallback", "rag": False, "cache": False, "avisos": ["Resposta de exemplo (mock)."],
        "metricas": {"latenciaMs": 0, "modelo": "mock", "tokensEntrada": 0, "tokensSaida": 0,
                     "custoEstimadoUsd": 0.0},
        "_links": {"buscarPrestadores": {"href": "/v1/prestadores?categoria=eletricista", "method": "GET"},
                   "criarSolicitacao": {"href": "/v1/solicitacoes", "method": "POST"}},
    }


def avaliacao_criada(solicitacao_id: str, prestador_id: str, nota: int) -> dict:
    return {"id": "aval_mock", "solicitacaoId": solicitacao_id, "prestadorId": prestador_id, "nota": nota,
            "_links": {"prestador": {"href": f"/v1/prestadores/{prestador_id}", "method": "GET"}}}
