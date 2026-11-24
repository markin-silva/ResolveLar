"""Usuários fixos de demonstração, pré-cadastrados para que qualquer integrante teste sem criar conta.

Os ids dos prestadores batem com o seed do ms-prestadores (CQRS) e os dos contratantes com as avaliações
de exemplo. A senha NÃO fica aqui: vem de DEMO_PASSWORD.
"""

# perfil -> `iss` do JWT (a `key` da credencial no Kong) e rótulo exibido na tela de entrada
PERFIS = {
    "contratante": {"iss": "contratante-key"},
    "prestador": {"iss": "prestador-key"},
}

USUARIOS = [
    # login, id (claim `sub`), nome, perfil, resumo mostrado na tela de entrada
    ("mariana", "contratante_15", "Mariana Alves", "contratante", "Contratante · Lavras"),
    ("rafael", "contratante_21", "Rafael Costa", "contratante", "Contratante · Lavras"),
    ("juliana", "contratante_22", "Juliana Ramos", "contratante", "Contratante · Lavras"),
    ("carlos", "prest_17", "Carlos Silva", "prestador", "Eletricista e instalador · Lavras"),
    ("ana", "prest_23", "Ana Souza", "prestador", "Eletricista · Lavras"),
    ("joao", "prest_31", "João Pereira", "prestador", "Encanador · Lavras"),
    ("rocha", "prest_32", "Hidráulica Rocha", "prestador", "Encanador e gás · Lavras"),
    ("marcosgas", "prest_41", "Marcos Gás & Cia", "prestador", "Técnico de gás · Lavras"),
    ("pedro", "prest_52", "Pedro Construções", "prestador", "Pedreiro · Lavras"),
    ("lucia", "prest_63", "Lúcia Pinturas", "prestador", "Pintora · Lavras"),
    ("chaveiro", "prest_74", "Chaveiro 24h Lavras", "prestador", "Chaveiro · Lavras"),
    ("marcenaria", "prest_85", "Marcenaria Oliveira", "prestador", "Marceneiro · Lavras"),
    ("refrigeracao", "prest_96", "Rafael Refrigeração", "prestador", "Instalador · Lavras"),
    ("bh", "prest_99", "Encanador BH", "prestador", "Encanador · Belo Horizonte"),
]

POR_LOGIN = {u[0]: u for u in USUARIOS}
