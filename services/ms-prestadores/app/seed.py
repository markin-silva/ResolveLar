"""Prestadores de exemplo (Lavras/MG). Cadastrados pelos COMANDOS, então geram eventos e populam o
Read DB pelo projetor, exatamente como um cadastro real. Os ids batem com os mocks dos BFFs e com o
consumer `prest_17` do Kong."""
import logging

from sqlmodel import Session

from app import commands
from app.database import write_engine

logger = logging.getLogger("app.seed")

PRESTADORES = [
    dict(prestadorId="prest_17", nome="Carlos Silva", email="carlos@exemplo.com", telefone="+55 35 99999-0017",
         categorias=["eletricista", "instalador"], bairrosAtendidos=["Centro", "Jardim Glória", "Vila Barão"],
         localizacao={"lat": -21.2453, "lon": -44.9999}, raioAtendimentoKm=15, precoMedioCentavos=15000),
    dict(prestadorId="prest_23", nome="Ana Souza", email="ana@exemplo.com", telefone="+55 35 99999-0023",
         categorias=["eletricista"], bairrosAtendidos=["Centro", "Jardim Floresta"], precoMedioCentavos=14000),
    dict(prestadorId="prest_31", nome="João Pereira", email="joao@exemplo.com", telefone="+55 35 99999-0031",
         categorias=["encanador"], bairrosAtendidos=["Centro", "Santa Efigênia"], precoMedioCentavos=12000),
    dict(prestadorId="prest_32", nome="Hidráulica Rocha", email="rocha@exemplo.com",
         categorias=["encanador", "tecnico-gas"], bairrosAtendidos=["Centro", "Vila Ester"], precoMedioCentavos=16000),
    dict(prestadorId="prest_41", nome="Marcos Gás & Cia", email="marcosgas@exemplo.com",
         categorias=["tecnico-gas"], bairrosAtendidos=["Centro"], precoMedioCentavos=18000),
    dict(prestadorId="prest_52", nome="Pedro Construções", email="pedro@exemplo.com",
         categorias=["pedreiro"], bairrosAtendidos=["Centro", "Nova Lavras"], precoMedioCentavos=20000),
    dict(prestadorId="prest_63", nome="Lúcia Pinturas", email="lucia@exemplo.com",
         categorias=["pintor"], bairrosAtendidos=["Centro"], precoMedioCentavos=10000),
    dict(prestadorId="prest_74", nome="Chaveiro 24h Lavras", email="chaveiro@exemplo.com",
         categorias=["chaveiro"], bairrosAtendidos=["Centro", "Jardim Glória"], precoMedioCentavos=8000),
    dict(prestadorId="prest_85", nome="Marcenaria Oliveira", email="marcenaria@exemplo.com",
         categorias=["marceneiro"], bairrosAtendidos=["Centro"], precoMedioCentavos=22000),
    dict(prestadorId="prest_96", nome="Rafael Refrigeração", email="rafael@exemplo.com",
         categorias=["instalador"], bairrosAtendidos=["Centro"], precoMedioCentavos=17000),
    dict(prestadorId="prest_99", nome="Encanador BH", email="bh@exemplo.com", cidade="Belo Horizonte",
         categorias=["encanador"], precoMedioCentavos=13000),
]


def run() -> None:
    with Session(write_engine()) as s:
        if not commands.vazio(s):
            return
        for dados in PRESTADORES:
            dados = {"cidade": "Lavras", "uf": "MG", **dados}
            commands.cadastrar(s, commands.CadastrarPrestador(**dados))
    logger.info("Seed: %s prestadores cadastrados (eventos na outbox)", len(PRESTADORES))
