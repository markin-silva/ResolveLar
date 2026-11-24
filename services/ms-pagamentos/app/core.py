"""Infra local; mantido igual nos três serviços para builds independentes."""
import asyncio
import hashlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import URL, text
from sqlmodel import SQLModel, Session, create_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("resolvelar")
logging.basicConfig(level=logging.INFO)


def now():
    return datetime.now(timezone.utc)


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def database_url():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return URL.create("postgresql+psycopg", username=os.environ["POSTGRES_USER"],
                      password=os.environ["POSTGRES_PASSWORD"], host=os.environ["DB_HOST"],
                      database=os.environ["DB_NAME"])


engine = create_engine(database_url(), pool_pre_ping=True)


def lock(session, key):
    """Serializa comandos concorrentes, inclusive quando o registro ainda não existe."""
    if engine.dialect.name == "postgresql":
        value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=value))


def require(session, model, key):
    row = session.get(model, key)
    if row is None:
        raise HTTPException(404, "Recurso não encontrado")
    return row


def identity(request, role=None):
    user = request.headers.get("X-User-Id")
    if not user:
        raise HTTPException(401, "Identidade ausente")
    if role and request.headers.get("X-User-Role") != role:
        raise HTTPException(403, "Perfil não autorizado")
    return user


async def repeat(action):
    while True:
        try:
            await action()
        except Exception:
            log.exception("Worker falhou; nova tentativa em 1s")
        await asyncio.sleep(1)


def create_app(name, workers=()):
    @asynccontextmanager
    async def lifespan(app):
        with Session(engine) as session, session.begin():
            lock(session, "schema:init")
            SQLModel.metadata.create_all(session.connection())
        tasks = [asyncio.create_task(worker()) for worker in workers]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            engine.dispose()

    app = FastAPI(title=name, lifespan=lifespan)

    @app.middleware("http")
    async def correlation(request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-Id") or uid("corr")
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    def problem(request, status, detail):
        return JSONResponse({"type": "about:blank", "title": detail, "status": status,
                             "detail": detail, "instance": request.url.path},
                            status_code=status, media_type="application/problem+json")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return problem(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return problem(request, 422, "Corpo ou parâmetros inválidos")

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.error("Erro interno correlation_id=%s", request.state.correlation_id, exc_info=exc)
        return problem(request, 500, "Erro interno inesperado")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": name}

    @app.get("/ready")
    def ready():
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        return {"status": "ok"}

    return app
