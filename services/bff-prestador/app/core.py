"""Núcleo compartilhado dos BFFs (arquivo IDÊNTICO em bff-contratante e bff-prestador).

Se alterar aqui, copie para o outro BFF:  cp services/bff-contratante/app/core.py services/bff-prestador/app/core.py
"""
import logging
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings

logger = logging.getLogger("bff")
PROBLEM_JSON = "application/problem+json"
# Hostname do contêiner (X-Pod-Name): mostra qual réplica respondeu, útil com `docker compose up --scale`.
POD_NAME = socket.gethostname()


# --------------------------------------------------------------------------- erros
class ApiError(Exception):
    """Erro de negócio/infra do BFF, devolvido como RFC 7807."""

    def __init__(self, status: int, title: str, detail: str | None = None):
        self.status, self.title, self.detail = status, title, detail


class UpstreamError(Exception):
    """Microsserviço respondeu 4xx/5xx: o BFF repassa o erro."""

    def __init__(self, response: httpx.Response):
        self.response = response


def problem(request: Request, status: int, title: str, detail: str | None = None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail,
            "instance": request.url.path, **extra}
    response = JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        response.headers["X-Correlation-Id"] = cid
    return response


# --------------------------------------------------------------------------- identidade
@dataclass
class User:
    id: str
    role: str | None = None


def current_user(
    x_consumer_username: str | None = Header(None),
    x_user_id: str | None = Header(None),
    x_consumer_groups: str | None = Header(None),
) -> User:
    """Identidade injetada pelo Kong após validar o JWT (X-Consumer-Username / X-Consumer-Groups).

    `X-User-Id` é fallback para testar o BFF direto, sem Kong. O BFF confia nesses
    headers porque só é acessível pela rede interna.
    """
    user_id = x_consumer_username or x_user_id
    if not user_id:
        raise ApiError(401, "Unauthorized", "Identidade ausente: esperado X-Consumer-Username (Kong) ou X-User-Id.")
    return User(id=user_id, role=x_consumer_groups)


# --------------------------------------------------------------------------- chamadas internas
def new_client(timeout: float | None = None) -> httpx.AsyncClient:
    """Todas as chamadas internas usam timeout curto (padrão 3s; a triagem IA passa um maior)."""
    return httpx.AsyncClient(timeout=timeout or get_settings().HTTP_TIMEOUT_SECONDS)


def upstream_headers(request: Request, user: User, **extra: str | None) -> dict[str, str]:
    headers = {
        "X-Correlation-Id": getattr(request.state, "correlation_id", ""),
        "X-User-Id": user.id,
        "X-User-Role": user.role or "",
    }
    headers.update({k: v for k, v in extra.items() if v})
    return headers


def unwrap(request: Request, result: Any, mock: Any, *, essential: bool = True) -> Any:
    """Converte um item de `asyncio.gather(..., return_exceptions=True)` em dados.

    - Response 2xx            -> JSON
    - Response 4xx/5xx        -> repassa o erro (essencial) ou None (opcional)
    - httpx.RequestError      -> mock, se ENABLE_UPSTREAM_MOCK=true (serviço ainda não existe);
                                 senão 503 (essencial) ou None = bloco omitido (degradação graciosa)
    """
    if isinstance(result, httpx.Response):
        if result.is_success:
            return result.json() if result.content else None
        if essential:
            raise UpstreamError(result)
        return None
    if isinstance(result, httpx.RequestError):
        if get_settings().ENABLE_UPSTREAM_MOCK:
            request.state.mocked = True
            return mock() if callable(mock) else mock
        logger.warning("upstream indisponível: %s", type(result).__name__)
        if essential:
            raise ApiError(503, "Service Unavailable", "Um serviço interno necessário está indisponível.")
        return None
    if essential:
        raise ApiError(502, "Bad Gateway", "Resposta inesperada de um serviço interno.")
    return None


async def forward_write(
    request: Request, method: str, url: str, user: User, body: dict, *,
    mock_status: int, mock_body: dict, idempotency_key: str | None = None, timeout: float | None = None,
) -> Response:
    """Repassa um comando (POST) ao microsserviço e devolve status/corpo originais."""
    headers = upstream_headers(request, user, **{"Idempotency-Key": idempotency_key})
    try:
        async with new_client(timeout) as client:
            resp = await client.request(method, url, json=body, headers=headers)
    except httpx.RequestError as exc:
        if get_settings().ENABLE_UPSTREAM_MOCK:
            request.state.mocked = True
            return JSONResponse(mock_body, status_code=mock_status)
        logger.warning("upstream indisponível: %s", type(exc).__name__)
        raise ApiError(503, "Service Unavailable", "O serviço interno está indisponível.") from exc
    out_headers = {"Location": resp.headers["location"]} if "location" in resp.headers else {}
    return Response(resp.content, status_code=resp.status_code, headers=out_headers,
                    media_type=resp.headers.get("content-type", "application/json"))


# --------------------------------------------------------------------------- utilidades
def pick(data: Any, *keys: str, default: Any = None) -> Any:
    """Primeiro campo presente (tolera camelCase e snake_case entre as docs)."""
    if isinstance(data, dict):
        for key in keys:
            if data.get(key) is not None:
                return data[key]
    return default


def as_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "orcamentos", "content", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def as_first(data: Any) -> dict | None:
    items = as_list(data) if not (isinstance(data, dict) and "items" not in data) else [data]
    return items[0] if items else None


def brl(centavos: int) -> str:
    reais, cents = divmod(int(centavos), 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"


# --------------------------------------------------------------------------- app
def create_app(title: str) -> FastAPI:
    app = FastAPI(title=title)
    settings = get_settings()

    @app.middleware("http")
    async def base_middleware(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.mocked = False
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        response.headers["X-Pod-Name"] = POD_NAME
        if request.state.mocked:
            response.headers["X-Mock-Upstream"] = "true"
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.title, exc.detail)

    @app.exception_handler(UpstreamError)
    async def upstream_error_handler(request: Request, exc: UpstreamError):
        resp = exc.response
        if PROBLEM_JSON in resp.headers.get("content-type", ""):
            return Response(resp.content, status_code=resp.status_code, media_type=PROBLEM_JSON)
        return problem(request, resp.status_code, "Erro em serviço interno", resp.text[:200] or None)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return problem(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(request, 422, "Validation Error", "Corpo ou parâmetros inválidos.", errors=errors)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Erro não tratado (correlation_id=%s)", getattr(request.state, "correlation_id", None))
        return problem(request, 500, "Internal Server Error", "Erro interno inesperado.")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": settings.SERVICE_NAME, "pod": POD_NAME,
                "mockUpstream": settings.ENABLE_UPSTREAM_MOCK}

    return app
