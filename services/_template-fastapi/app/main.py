import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings

logger = logging.getLogger("app")
settings = get_settings()

app = FastAPI(title=settings.SERVICE_NAME)

PROBLEM_JSON = "application/problem+json"


def problem(request: Request, status: int, title: str, detail: str | None = None, **extra) -> JSONResponse:
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        **extra,
    }
    response = JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        response.headers["X-Correlation-Id"] = cid
    return response


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = cid
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return problem(request, exc.status_code, str(exc.detail), None)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return problem(request, 422, "Validation Error", "Corpo ou parâmetros inválidos.", errors=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Erro não tratado (correlation_id=%s)", getattr(request.state, "correlation_id", None))
    return problem(request, 500, "Internal Server Error", "Erro interno inesperado.")


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}
