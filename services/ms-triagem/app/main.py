"""ms-triagem — Assistente de Triagem Residencial (LangChain + ChromaDB + resiliência)."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request

from app import triagem
from app.config import get_settings
from app.http import install
from app.rag import BaseConhecimento
from app.schemas import TriagemIn
from app.tools import correlation_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    def _init():
        b = BaseConhecimento(settings.CHROMA_PATH)
        n = b.indexar()
        logger.info("Base de conhecimento pronta: %s chunks; LLM=%s (%s)", n, settings.provider(), settings.model())
        return b

    triagem.base = await asyncio.to_thread(_init)
    yield


app = FastAPI(title="ms-triagem", version="1.0.0", lifespan=lifespan)
install(app)


@app.get("/health")
def health():
    return {
        "status": "ok", "service": settings.SERVICE_NAME,
        "llm": {"provedor": settings.provider(), "modelo": settings.model(), "circuitBreaker": triagem.breaker.estado},
        "rag": {"chunks": triagem.base.total() if triagem.base else 0},
    }


@app.post("/v1/triagem")
async def triar(body: TriagemIn, request: Request,
                rag: bool = Query(True, description="false = sem contexto do RAG (usado na avaliação)"),
                cache: bool = Query(True, description="false = ignora o cache Redis")):
    correlation_id.set(getattr(request.state, "correlation_id", ""))
    return await triagem.triar(body, usar_rag=rag, usar_cache=cache)


@app.get("/v1/triagem/base-conhecimento")
async def buscar_base(q: str = Query(min_length=3), k: int = Query(4, ge=1, le=10)):
    """Depuração do RAG: mostra os trechos que seriam enviados ao LLM."""
    return {"items": await asyncio.to_thread(triagem.base.buscar, q, k)}
