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
