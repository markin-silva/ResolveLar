"""ms-auth — login dos usuários fixos de demonstração e emissão do JWT (HS256).

O Kong continua validando assinatura, expiração e perfil; este serviço só emite o token. Não há banco,
registro de contas nem dados de domínio: a lista de usuários é fixa (app/usuarios.py) e a senha vem do ambiente.
"""
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.usuarios import PERFIS, POR_LOGIN, USUARIOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")
settings = get_settings()

if not settings.JWT_SECRET or not settings.DEMO_PASSWORD:
    # Falha cedo e alto: melhor não subir do que emitir tokens com segredo vazio.
    raise RuntimeError("JWT_SECRET e DEMO_PASSWORD são obrigatórios (defina no .env)")

app = FastAPI(title="ms-auth", version="1.0.0")
PROBLEM_JSON = "application/problem+json"


def problem(request: Request, status: int, title: str, detail: str | None = None) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, "instance": request.url.path}
    response = JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        response.headers["X-Correlation-Id"] = cid
    return response


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request.state.correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = request.state.correlation_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception(request: Request, exc: StarletteHTTPException):
    return problem(request, exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception(request: Request, exc: RequestValidationError):
    return problem(request, 422, "Validation Error", "Corpo inválido: informe usuario e senha.")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def emitir_token(iss: str, sub: str) -> tuple[str, int]:
    agora = int(time.time())
    exp = agora + int(settings.JWT_TTL_HOURS * 3600)
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"iss": iss, "sub": sub, "iat": agora, "exp": exp}, separators=(",", ":")).encode())
    sig = hmac.new(settings.JWT_SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}", exp - agora


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=64)
    senha: str = Field(min_length=1, max_length=128)


def publico(u: tuple) -> dict:
    login, uid, nome, perfil, resumo = u
    return {"usuario": login, "id": uid, "nome": nome, "perfil": perfil, "resumo": resumo}


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/v1/auth/usuarios")
def listar_usuarios():
    """Usuários de demonstração para a tela de entrada (sem senha). A senha é informada em separado."""
    return {"items": [publico(u) for u in USUARIOS]}


@app.post("/v1/auth/login")
def login(body: LoginIn, request: Request):
    u = POR_LOGIN.get(body.usuario.strip().lower())
    # compare_digest nos dois casos: o tempo de resposta não revela se o usuário existe
    senha_ok = hmac.compare_digest(body.senha.encode(), settings.DEMO_PASSWORD.encode())
    if u is None or not senha_ok:
        logger.info("login recusado (usuario=%s) correlationId=%s", body.usuario[:32], request.state.correlation_id)
        return problem(request, 401, "Unauthorized", "Usuário ou senha inválidos.")
    token, expira_em = emitir_token(PERFIS[u[3]]["iss"], u[1])
    logger.info("login ok usuario=%s perfil=%s correlationId=%s", u[0], u[3], request.state.correlation_id)
    return {"access_token": token, "token_type": "Bearer", "expires_in": expira_em, "usuario": publico(u)}
