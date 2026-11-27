"""Assistente de Triagem Residencial — cadeia LCEL completa:

    entrada ──► RAG (ChromaDB) ──► prompt | LLM (timeout + retry + circuit breaker, ou fallback por regras)
            ──► tool buscar_prestadores (ms-prestadores real) ──► resposta

O LLM nunca escolhe nem inventa prestadores: a tool é chamada pela cadeia com a categoria classificada,
então todo prestador sugerido existe no Read DB do ms-prestadores.
"""
import asyncio
import hashlib
import logging
import time
import uuid

from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app import fallback
from app.config import get_settings
from app.llm import SEM_CONTEXTO, classificador
from app.rag import BaseConhecimento
from app.resiliencia import CircuitBreaker, cache_get, cache_set
from app.schemas import Classificacao, TriagemIn
from app.tools import buscar_prestadores

logger = logging.getLogger("app.triagem")
settings = get_settings()

base: BaseConhecimento | None = None  # inicializada no lifespan
breaker = CircuitBreaker(settings.CIRCUIT_FAILURE_THRESHOLD, settings.CIRCUIT_RESET_SECONDS)


# ------------------------------------------------------------------ passos da cadeia
async def recuperar(x: dict) -> list[dict]:
    if not x["usar_rag"] or base is None:
        return []
    consulta = x["descricao"]
    return await asyncio.to_thread(base.buscar, consulta, settings.RAG_TOP_K)


def formatar_contexto(x: dict) -> str:
    if not x["docs"]:
        return SEM_CONTEXTO
    return "\n\n".join(f"[{d['fonte']} · {d['secao']}]\n{d['texto']}" for d in x["docs"])


RESERVA_TOOL_SECONDS = 0.6  # tempo guardado para a tool de prestadores depois do LLM


def _restante(x: dict) -> float:
    """Segundos que faltam para o prazo da triagem inteira (TRIAGEM_DEADLINE_SECONDS)."""
    return settings.TRIAGEM_DEADLINE_SECONDS - (time.perf_counter() - x["inicio"])


PERMANENTES = ("InvalidRequest", "BadRequest", "Authentication", "PermissionDenied", "NotFound")


def _transitorio(exc: BaseException) -> bool:
    """Timeout, 429, 5xx e saída fora do schema valem retry; chave inválida/requisição inválida não."""
    return not any(p in type(exc).__name__ for p in PERMANENTES)


async def _invocar_llm(entrada: dict) -> tuple[Classificacao, dict]:
    """Uma chamada ao LLM com retry/backoff; cada tentativa tem timeout próprio."""
    chain = classificador()
    async for tentativa in AsyncRetrying(stop=stop_after_attempt(1 + settings.LLM_MAX_RETRIES),
                                         wait=wait_exponential(multiplier=0.3, max=2),
                                         retry=retry_if_exception(_transitorio), reraise=True):
        with tentativa:
            out = await asyncio.wait_for(chain.ainvoke(entrada), timeout=settings.LLM_TIMEOUT_SECONDS)
            if out.get("parsed") is None:
                raise ValueError(f"saída do LLM fora do schema: {out.get('parsing_error')}")
            uso = getattr(out["raw"], "usage_metadata", None) or {}
            return out["parsed"], uso
    raise RuntimeError("inalcançável")


async def _com_teto(coro, segundos: float):
    """Teto rígido: estourou o tempo, segue sem esperar o cancelamento terminar.

    `asyncio.wait_for` aguarda a tarefa cancelada encerrar, e o SDK do LLM pode levar segundos para
    soltar a requisição HTTP em andamento; isso empurrava a resposta além do timeout do BFF (503).
    """
    tarefa = asyncio.ensure_future(coro)
    feitas, _ = await asyncio.wait({tarefa}, timeout=segundos)
    if not feitas:
        tarefa.cancel()
        tarefa.add_done_callback(lambda t: t.cancelled() or t.exception())  # evita "exception never retrieved"
        raise asyncio.TimeoutError(f"orçamento total do LLM ({segundos}s) esgotado")
    return tarefa.result()


async def classificar(x: dict) -> dict:
    """LLM com resiliência; qualquer falha cai no fallback determinístico (que também usa o RAG)."""
    avisos: list[str] = []
    entrada = {"descricao": x["descricao"], "cidade": x.get("cidade") or "não informada", "contexto": x["contexto"]}
    # o LLM usa o menor entre o seu orçamento e o que sobrou do prazo da triagem (menos a reserva da tool)
    orcamento = min(settings.LLM_TOTAL_BUDGET_SECONDS, _restante(x) - RESERVA_TOOL_SECONDS)
    if classificador() is None:
        avisos.append("LLM não configurado (sem chave de API): triagem por regras.")
    elif not breaker.permite():
        avisos.append("LLM temporariamente desativado após falhas seguidas (circuit breaker aberto): triagem por regras.")
    elif orcamento < 1.0:
        avisos.append("Sem tempo para consultar o LLM nesta requisição: triagem por regras.")
    else:
        try:
            resultado, uso = await _com_teto(_invocar_llm(entrada), orcamento)
            breaker.sucesso()
            return {"resultado": resultado, "modo": "llm", "uso": uso, "avisos": avisos}
        except Exception as exc:
            breaker.falha()
            logger.warning("LLM falhou (%s: %s); usando fallback", type(exc).__name__, str(exc)[:200])
            avisos.append(f"LLM indisponível ({type(exc).__name__}): triagem por regras.")
    return {"resultado": fallback.classificar(x["descricao"], x["docs"]), "modo": "fallback", "uso": {},
            "avisos": avisos}


async def sugerir_prestadores(x: dict) -> dict:
    c: Classificacao = x["llm"]["resultado"]
    try:
        prestadores = await asyncio.wait_for(
            buscar_prestadores.ainvoke({"categoria": c.categoria, "cidade": x.get("cidade")}),
            timeout=max(0.3, _restante(x)))
    except Exception as exc:
        logger.warning("Tool buscar_prestadores falhou: %s", type(exc).__name__)
        prestadores = []
        x["llm"]["avisos"].append("Não foi possível consultar prestadores agora; tente a busca em instantes.")
    return {**x, "prestadores": prestadores}


cadeia = (
    RunnablePassthrough.assign(docs=RunnableLambda(recuperar))
    | RunnablePassthrough.assign(contexto=RunnableLambda(formatar_contexto))
    | RunnablePassthrough.assign(llm=RunnableLambda(classificar))
    | RunnableLambda(sugerir_prestadores)
)


# ------------------------------------------------------------------ API pública do módulo
def _chave_cache(req: TriagemIn, usar_rag: bool) -> str:
    base_txt = f"{fallback.normalizar(req.descricao).strip()}|{(req.cidade or '').lower()}|{usar_rag}|{settings.model()}"
    return "triagem:v1:" + hashlib.sha256(base_txt.encode()).hexdigest()[:32]


def _custo(uso: dict) -> float:
    p_in, p_out = settings.precos()
    return round((uso.get("input_tokens", 0) * p_in + uso.get("output_tokens", 0) * p_out) / 1_000_000, 6)


async def triar(req: TriagemIn, usar_rag: bool = True, usar_cache: bool = True) -> dict:
    inicio = time.perf_counter()
    chave = _chave_cache(req, usar_rag)
    if usar_cache and (hit := await cache_get(chave)):
        hit["cache"] = True
        hit["metricas"] = {**hit["metricas"], "latenciaMs": round((time.perf_counter() - inicio) * 1000, 1),
                           "tokensEntrada": 0, "tokensSaida": 0, "custoEstimadoUsd": 0.0}
        return hit

    x = await cadeia.ainvoke({"descricao": req.descricao, "cidade": req.cidade, "usar_rag": usar_rag,
                              "inicio": inicio})
    c: Classificacao = x["llm"]["resultado"]
    uso, modo = x["llm"]["uso"], x["llm"]["modo"]
    avisos = x["llm"]["avisos"]
    if c.urgencia == "EMERGENCIA":
        avisos.insert(0, "EMERGÊNCIA: priorize a segurança e acione o serviço público antes do prestador.")

    params = f"categoria={c.categoria}" + (f"&cidade={req.cidade}" if req.cidade else "")
    resposta = {
        "triagemId": f"tri_{uuid.uuid4().hex[:10]}",
        "categoria": c.categoria,
        "urgencia": c.urgencia,
        "resumo": c.resumo,
        "orientacoesSeguranca": c.orientacoesSeguranca,
        "perguntasComplementares": c.perguntasComplementares[:2],
        "prestadoresSugeridos": x["prestadores"],
        "fontes": [{"documento": d["fonte"], "secao": d["secao"], "distancia": d["distancia"]} for d in x["docs"]],
        "modo": modo,
        "rag": usar_rag,
        "cache": False,
        "avisos": avisos,
        "metricas": {
            "latenciaMs": round((time.perf_counter() - inicio) * 1000, 1),
            "modelo": settings.model() if modo == "llm" else "regras",
            "tokensEntrada": uso.get("input_tokens", 0),
            "tokensSaida": uso.get("output_tokens", 0),
            "custoEstimadoUsd": _custo(uso),
        },
        "_links": {
            "buscarPrestadores": {"href": f"/v1/prestadores?{params}", "method": "GET"},
            "criarSolicitacao": {"href": "/v1/solicitacoes", "method": "POST", "title": "Abrir solicitação"},
        },
    }
    # só resultados do LLM vão para o cache: um fallback não deve "grudar" depois que o LLM voltar
    if usar_cache and modo == "llm":
        await cache_set(chave, resposta, settings.CACHE_TTL_SECONDS)
    return resposta
