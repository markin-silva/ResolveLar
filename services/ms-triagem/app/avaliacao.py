"""Avaliação do Assistente de Triagem: 5 perguntas, COM e SEM RAG, medindo acerto, latência e custo.

Roda dentro do contêiner (precisa do ms-prestadores e da base indexada):

    docker compose exec ms-triagem python -m app.avaliacao
    docker compose exec ms-triagem python -m app.avaliacao --saida /tmp/avaliacao.md
    docker compose cp ms-triagem:/tmp/avaliacao.md docs/05-avaliacao-triagem.md

Métricas por resposta:
- categoria correta e urgência aceitável (gabarito abaixo);
- cobertura de segurança: % dos grupos de palavras-chave (fatos da base de conhecimento) presentes nas
  orientações; cada grupo vale se QUALQUER termo dele aparecer;
- latência ponta a ponta da cadeia (sem cache), tokens e custo estimado (preço por 1M tokens do provedor).
"""
import argparse
import asyncio
import statistics
from datetime import datetime

from app import triagem
from app.config import get_settings
from app.fallback import normalizar
from app.rag import BaseConhecimento
from app.schemas import TriagemIn

PERGUNTAS = [
    {
        "descricao": "Meu chuveiro elétrico parou de esquentar e quando ligo no modo inverno o disjuntor desarma.",
        "categoria": "eletricista", "urgencias": {"MEDIA", "ALTA"},
        "seguranca": [["disjuntor"], ["amperagem", "maior"], ["fiacao", "fio", "queimad"], ["molhad", "seca"]],
    },
    {
        "descricao": "Estou sentindo um cheiro forte de gás na cozinha desde que acordei.",
        "categoria": "tecnico-gas", "urgencias": {"EMERGENCIA"},
        "seguranca": [["interruptor"], ["registro"], ["janela", "ventil"], ["193", "bombeiro"],
                      ["fosforo", "isqueiro", "chama", "acend"]],
    },
    {
        "descricao": "Apareceu uma mancha de umidade no teto do banheiro que aumenta depois do banho e começou a pingar.",
        "categoria": "encanador", "urgencias": {"MEDIA", "ALTA"},
        "seguranca": [["registro"], ["energia", "disjuntor", "luminaria"], ["de cima", "andar", "vizinho"],
                      ["forro", "nao toque"]],
    },
    {
        "descricao": "Cheguei em casa e a chave quebrou dentro da fechadura da porta da frente, estou do lado de fora.",
        "categoria": "chaveiro", "urgencias": {"ALTA", "MEDIA"},
        "seguranca": [["force", "forcar"], ["cola", "oleo"], ["pinca"], ["193", "bombeiro", "crianca"]],
    },
    {
        "descricao": "Surgiu uma rachadura diagonal grande na parede da sala, saindo do canto da janela, e está aumentando.",
        "categoria": "pedreiro", "urgencias": {"ALTA", "EMERGENCIA"},
        "seguranca": [["engenheiro"], ["lapis", "marque", "marcar", "foto", "regua"], ["199", "defesa civil"],
                      ["emperr", "estalo"]],
    },
]


def cobertura(resposta: dict, grupos: list[list[str]]) -> float:
    texto = normalizar(" ".join(resposta["orientacoesSeguranca"]))
    return sum(any(t in texto for t in g) for g in grupos) / len(grupos)


async def avaliar() -> list[dict]:
    linhas = []
    for i, q in enumerate(PERGUNTAS, 1):
        for usar_rag in (True, False):
            r = await triagem.triar(TriagemIn(descricao=q["descricao"], cidade="Lavras"),
                                    usar_rag=usar_rag, usar_cache=False)
            m = r["metricas"]
            linhas.append({
                "n": i, "rag": usar_rag, "modo": r["modo"], "categoria": r["categoria"],
                "cat_ok": r["categoria"] == q["categoria"], "urgencia": r["urgencia"],
                "urg_ok": r["urgencia"] in q["urgencias"], "cobertura": cobertura(r, q["seguranca"]),
                "fontes": len(r["fontes"]), "prestadores": len(r["prestadoresSugeridos"]),
                "latencia": m["latenciaMs"], "tin": m["tokensEntrada"], "tout": m["tokensSaida"],
                "custo": m["custoEstimadoUsd"], "orientacoes": r["orientacoesSeguranca"],
            })
    return linhas


VOLUMES_MES = [1_000, 100_000, 1_000_000]


def percentil(valores: list[float], p: float) -> float:
    v = sorted(valores)
    return v[min(len(v) - 1, max(0, round(p * (len(v) - 1))))]


def escala(linhas: list[dict], taxa_cache: float, orcamento_s: float) -> list[str]:
    """Latência p50/p95 das chamadas ao LLM e custo projetado por volume mensal (com e sem cache)."""
    llm = [l for l in linhas if l["modo"] == "llm"]
    out = ["", "## Latência e custo em escala", ""]
    if not llm:
        return out + ["Nenhuma resposta veio do LLM nesta execução (sem chave ou provedor indisponível): "
                      "não há base para projetar custo."]
    lat = [l["latencia"] for l in llm]
    acima = sum(l > orcamento_s * 1000 for l in lat)
    out += [
        f"- Respostas do LLM: {len(llm)}/{len(linhas)}. Latência p50 = {percentil(lat, .5):.0f} ms, "
        f"p95 = {percentil(lat, .95):.0f} ms, máx = {max(lat):.0f} ms.",
        f"- {acima}/{len(llm)} chamadas passaram do orçamento de produção ({orcamento_s:.0f} s): em produção essas "
        "cairiam no fallback por regras (a resposta chega, só que sem o LLM).", "",
        "| Configuração | Tokens médios (in/out) | Custo/consulta (US$) | "
        + " | ".join(f"{v:,}/mês".replace(",", ".") for v in VOLUMES_MES)
        + f" | {VOLUMES_MES[-1]:,}/mês com {taxa_cache:.0%} de cache".replace(",", ".") + " |",
        "|---|---|---|" + "---|" * (len(VOLUMES_MES) + 1),
    ]
    for usar_rag in (True, False):
        g = [l for l in llm if l["rag"] == usar_rag]
        if not g:
            continue
        c = statistics.mean(l["custo"] for l in g)
        out.append(
            f"| {'Com RAG' if usar_rag else 'Sem RAG'} | {statistics.mean(l['tin'] for l in g):.0f}/"
            f"{statistics.mean(l['tout'] for l in g):.0f} | {c:.6f} | "
            + " | ".join(f"US$ {c * v:,.2f}" for v in VOLUMES_MES)
            + f" | US$ {c * VOLUMES_MES[-1] * (1 - taxa_cache):,.2f} |")
    out += ["", "Leitura: o custo cresce linearmente com o volume; o cache por chave (`triagem:v1:*`, 1 h) só "
            "economiza em descrições repetidas, por isso a taxa de acerto é uma hipótese (`--taxa-cache`). "
            "O RAG aumenta os tokens de entrada (contexto), mas a saída domina o preço."]
    return out


def relatorio(linhas: list[dict], taxa_cache: float = 0.2, orcamento_s: float | None = None,
              timeout_s: float | None = None) -> str:
    s = get_settings()
    orcamento_s = orcamento_s or s.LLM_TOTAL_BUDGET_SECONDS
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    out = [
        "# Avaliação do Assistente de Triagem (RAG × sem RAG)", "",
        f"- Data: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Provedor/modelo: `{s.provider()}` / `{s.model() or 'regras (fallback)'}`",
        f"- Preço usado: US$ {s.precos()[0]}/1M tokens de entrada, US$ {s.precos()[1]}/1M de saída (estimativa)",
        "- Cache desligado; latência = cadeia completa (RAG + LLM + tool de prestadores).",
        f"- Timeout do LLM nesta avaliação: {timeout_s or s.LLM_TIMEOUT_SECONDS:.0f} s por tentativa, com retry em 503/timeout "
        f"(produção: orçamento total de {orcamento_s:.0f} s; acima disso a triagem cai no fallback).", "",
        "| # | RAG | Modo | Categoria | Urgência | Cobertura segurança | Fontes | Prestadores | Latência (ms) | Tokens (in/out) | Custo (US$) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for l in linhas:
        out.append(f"| {l['n']} | {'sim' if l['rag'] else 'não'} | {l['modo']} | {ok(l['cat_ok'])} {l['categoria']} | "
                   f"{ok(l['urg_ok'])} {l['urgencia']} | {l['cobertura']:.0%} | {l['fontes']} | {l['prestadores']} | "
                   f"{l['latencia']:.0f} | {l['tin']}/{l['tout']} | {l['custo']:.6f} |")

    out += ["", "## Resumo", "",
            "| Configuração | Categoria correta | Urgência aceitável | Cobertura média | Latência média (ms) | Latência máx (ms) | Custo total (US$) | Custo médio/consulta (US$) |",
            "|---|---|---|---|---|---|---|---|"]
    for usar_rag in (True, False):
        g = [l for l in linhas if l["rag"] == usar_rag]
        out.append(
            f"| {'Com RAG' if usar_rag else 'Sem RAG'} | {sum(l['cat_ok'] for l in g)}/{len(g)} | "
            f"{sum(l['urg_ok'] for l in g)}/{len(g)} | {statistics.mean(l['cobertura'] for l in g):.0%} | "
            f"{statistics.mean(l['latencia'] for l in g):.0f} | {max(l['latencia'] for l in g):.0f} | "
            f"{sum(l['custo'] for l in g):.6f} | {statistics.mean(l['custo'] for l in g):.6f} |")

    out += escala(linhas, taxa_cache, orcamento_s)

    out += ["", "## Orientações geradas", ""]
    for l in linhas:
        out.append(f"**{l['n']} · {'com' if l['rag'] else 'sem'} RAG ({l['modo']})**: " + " / ".join(l["orientacoes"]))
        out.append("")
    return "\n".join(out)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", default="/tmp/avaliacao-triagem.md")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="timeout do LLM só nesta avaliação (mede a qualidade mesmo com o provedor lento)")
    parser.add_argument("--retries", type=int, default=3, help="retries extras do LLM só nesta avaliação")
    parser.add_argument("--taxa-cache", type=float, default=0.2, help="hipótese de acerto do cache na projeção")
    args = parser.parse_args()

    # orçamento de produção, guardado antes de afrouxar os limites só para esta execução
    s = triagem.settings
    orcamento_producao = s.LLM_TOTAL_BUDGET_SECONDS
    s.LLM_TIMEOUT_SECONDS = args.timeout
    s.LLM_TOTAL_BUDGET_SECONDS = args.timeout * (1 + args.retries)
    s.LLM_MAX_RETRIES = args.retries  # só erros transitórios (503/timeout) são repetidos
    s.TRIAGEM_DEADLINE_SECONDS = s.LLM_TOTAL_BUDGET_SECONDS + 10  # o prazo da triagem não corta o LLM aqui
    triagem.breaker.threshold = 10_000  # o breaker não deve "contaminar" as perguntas seguintes

    # índice próprio (mesmos .md): não disputa o diretório do Chroma com o servidor em execução
    triagem.base = BaseConhecimento("/tmp/chroma-avaliacao")
    triagem.base.indexar()
    md = relatorio(await avaliar(), args.taxa_cache, orcamento_producao, args.timeout)
    with open(args.saida, "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print(md)
    print(f"\nRelatório salvo em {args.saida}")


if __name__ == "__main__":
    asyncio.run(main())
