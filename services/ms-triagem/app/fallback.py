"""Fallback determinístico (sem LLM): regras por palavra-chave + orientações tiradas dos trechos do RAG.

Usado quando não há chave de API, o LLM estoura o timeout/retries ou o circuit breaker está aberto.
"""
import re
import unicodedata

from app.schemas import Classificacao


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.lower())


# ordem = prioridade no empate (gás primeiro: é o mais perigoso)
REGRAS: list[tuple[str, list[str]]] = [
    ("tecnico-gas", ["gas", "botijao", "fogao", "aquecedor a gas", "regulador"]),
    ("eletricista", ["chuveiro", "disjuntor", "tomada", "fio", "fiacao", "energia", "choque", "curto",
                     "interruptor", "lampada", "faisca", "quadro de luz", "sem luz"]),
    ("chaveiro", ["chave", "fechadura", "trancad", "cadeado", "porta travou"]),
    ("encanador", ["vazamento", "vazando", "vaza", "cano", "torneira", "registro", "descarga", "entup", "esgoto",
                   "ralo", "caixa d", "agua", "umidade", "goteira", "pinga", "hidrometro", "pia"]),
    ("pedreiro", ["rachadura", "trinca", "fissura", "reboco", "piso", "telha", "muro", "parede"]),
    ("pintor", ["pintura", "pintar", "tinta", "mofo", "bolor"]),
    ("marceneiro", ["armario", "movel", "moveis", "madeira", "gaveta", "dobradica"]),
    ("instalador", ["ar-condicionado", "ar condicionado", "instalar", "suporte", "tv", "maquina de lavar",
                    "ventilador", "coifa"]),
]

URGENCIA: list[tuple[str, list[str]]] = [
    ("EMERGENCIA", ["cheiro de gas", "cheiro forte de gas", "vazamento de gas", "fogo", "fumaca", "faisca",
                    "incendio", "levou choque", "tomou choque", "desab", "estalo"]),
    ("ALTA", ["desarma", "sem agua", "sem energia", "sem luz", "trancad", "do lado de fora", "esgoto volt",
              "alag", "nao para", "rachadura grande", "rachadura diagonal", "aumentando", "crescendo"]),
    ("BAIXA", ["pintar", "pintura", "instalar", "prateleira", "suporte", "planejad", "orcamento para"]),
]

GENERICAS = {
    "tecnico-gas": ["Feche o registro do gás e ventile o ambiente.", "Não acenda chamas nem acione interruptores."],
    "eletricista": ["Desligue o disjuntor do circuito antes de mexer em qualquer ponto elétrico."],
    "encanador": ["Feche o registro de água se houver vazamento ativo."],
    "pedreiro": ["Afaste móveis e pessoas da área afetada e acompanhe se a rachadura aumenta."],
    "chaveiro": ["Não force a fechadura."],
}
CHAMADAS = {"EMERGENCIA": "Se houver risco imediato, ligue para os Bombeiros (193) ou o SAMU (192)."}


def _pontuar(texto: str, regras: list[tuple[str, list[str]]]) -> str | None:
    melhor, pontos = None, 0
    for nome, termos in regras:
        p = sum(texto.count(t) for t in termos)
        if p > pontos:
            melhor, pontos = nome, p
    return melhor


def _urgencia(texto: str) -> str:
    for nivel, termos in URGENCIA:  # primeira regra que casar (EMERGENCIA > ALTA > BAIXA)
        if any(t in texto for t in termos):
            return nivel
    return "MEDIA"


def _orientacoes(docs: list[dict], limite: int = 4) -> list[str]:
    """Frases dos trechos de segurança recuperados (ignora categorias/urgência, que são descritivos)."""
    frases: list[str] = []
    for d in docs:
        if d["fonte"] in ("categorias.md", "urgencia.md"):
            continue
        corpo = d["texto"].split("\n", 1)[-1]
        for frase in re.split(r"(?<=[.!?])\s+", corpo):
            frase = frase.strip()
            if 20 <= len(frase) <= 260 and frase not in frases:
                frases.append(frase)
            if len(frases) >= limite:
                return frases
    return frases


def classificar(descricao: str, docs: list[dict]) -> Classificacao:
    texto = normalizar(descricao)
    categoria = _pontuar(texto, REGRAS) or "encanador"
    urgencia = _urgencia(texto)
    orientacoes = _orientacoes(docs) or list(GENERICAS.get(categoria, []))
    if urgencia in CHAMADAS:
        orientacoes.insert(0, CHAMADAS[urgencia])
    return Classificacao(
        categoria=categoria, urgencia=urgencia,
        resumo=descricao.strip()[:160],
        orientacoesSeguranca=orientacoes[:5],
        perguntasComplementares=["Desde quando o problema acontece?", "Pode enviar uma foto do local?"],
    )
