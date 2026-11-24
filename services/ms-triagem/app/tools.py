"""Tool LangChain que consulta prestadores REAIS no ms-prestadores (Read DB do CQRS)."""
import contextvars
import logging

import httpx
from langchain_core.tools import tool
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger("app.tools")
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def _transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):  # timeout, conexão recusada...
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


@tool
async def buscar_prestadores(categoria: str, cidade: str | None = None) -> list[dict]:
    """Busca prestadores ativos do ResolveLar por categoria de serviço e cidade, ordenados pela nota média.

    Args:
        categoria: slug da categoria (eletricista, encanador, tecnico-gas, pedreiro, pintor, marceneiro,
            chaveiro, instalador).
        cidade: cidade do atendimento (opcional).
    """
    s = get_settings()
    params = {"categoria": categoria, "size": 3, **({"cidade": cidade} if cidade else {})}
    async for tentativa in AsyncRetrying(stop=stop_after_attempt(1 + s.TOOL_MAX_RETRIES),
                                         wait=wait_exponential(multiplier=0.2, max=1),
                                         retry=retry_if_exception(_transitorio), reraise=True):
        with tentativa:
            async with httpx.AsyncClient(timeout=s.TOOL_TIMEOUT_SECONDS) as client:
                r = await client.get(f"{s.MS_PRESTADORES_URL}/v1/prestadores", params=params,
                                     headers={"X-Correlation-Id": correlation_id.get()})
                r.raise_for_status()
    return [
        {"prestadorId": p["prestadorId"], "nome": p["nome"], "categorias": p.get("categorias", []),
         "cidade": p.get("cidade"), "notaMedia": p.get("notaMedia"), "totalAvaliacoes": p.get("totalAvaliacoes"),
         "disponivelHoje": p.get("disponivelHoje"), "precoMedioCentavos": p.get("precoMedioCentavos"),
         "_links": {"self": {"href": f"/v1/prestadores/{p['prestadorId']}", "method": "GET"}}}
        for p in r.json().get("items", [])
    ]
