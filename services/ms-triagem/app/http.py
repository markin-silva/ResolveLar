"""Erros RFC 7807 e X-Correlation-Id (mesmo padrão de services/_template-fastapi).

Arquivo idêntico em ms-prestadores, ms-avaliacoes e ms-triagem. Alterou? Copie para os outros.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app")
PROBLEM_JSON = "application/problem+json"


class ApiError(Exception):
    """Erro de negócio devolvido como RFC 7807."""

    def __init__(self, status: int, title: str, detail: str | None = None, type_: str = "about:blank"):
        self.status, self.title, self.detail, self.type = status, title, detail, type_


def problem(request: Request, status: int, title: str, detail: str | None = None,
            type_: str = "about:blank", **extra) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "detail": detail,
            "instance": request.url.path, **extra}
    response = JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        response.headers["X-Correlation-Id"] = cid
    return response


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.title, exc.detail, exc.type)

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
