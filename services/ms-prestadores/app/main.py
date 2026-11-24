"""ms-prestadores — CQRS (docs/04, seção 3).

Comandos -> db-prestadores-write (+ outbox) | Relay -> RabbitMQ | Projetor -> db-prestadores-read | Queries + Redis.
O relay e o projetor rodam como tasks asyncio dentro do próprio serviço (sem contêiner extra).
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Query, Response
from sqlmodel import Session

from app import commands, queries, seed
from app.config import get_settings
from app.database import create_schemas, write_engine
from app.http import ApiError, install
from app.messaging import outbox_relay
from app.projector import run_projector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(create_schemas)
    if settings.SEED_DEMO_DATA:
        await asyncio.to_thread(seed.run)
    tasks = [asyncio.create_task(outbox_relay(), name="outbox-relay"),
             asyncio.create_task(run_projector(), name="projetor")]
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="ms-prestadores", version="1.0.0", lifespan=lifespan)
install(app)


def autorizar_escrita(prestador_id: str | None, user_id: str | None, role: str | None) -> None:
    """Contratante não escreve; prestador só altera o próprio cadastro. Sem headers = chamada interna."""
    if role == "contratante":
        raise ApiError(403, "Forbidden", "Contratantes não podem alterar cadastros de prestadores.")
    if role == "prestador" and prestador_id and user_id != prestador_id:
        raise ApiError(403, "Forbidden", "Um prestador só pode alterar o próprio cadastro.")


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


# ------------------------------------------------------------------ comandos (Write DB)
@app.post("/v1/prestadores", status_code=201)
def cadastrar(body: commands.CadastrarPrestador, response: Response,
              x_user_id: str | None = Header(None), x_user_role: str | None = Header(None)):
    autorizar_escrita(body.prestadorId, x_user_id, x_user_role)
    if x_user_role == "prestador" and not body.prestadorId:
        body.prestadorId = x_user_id
    with Session(write_engine()) as s:
        p = commands.cadastrar(s, body)
        response.headers["Location"] = f"/v1/prestadores/{p.id}"
        return commands.representar(p)


@app.patch("/v1/prestadores/{prestador_id}")
def atualizar_perfil(prestador_id: str, body: commands.AtualizarPerfil,
                     x_user_id: str | None = Header(None), x_user_role: str | None = Header(None)):
    autorizar_escrita(prestador_id, x_user_id, x_user_role)
    with Session(write_engine()) as s:
        return commands.representar(commands.atualizar_perfil(s, prestador_id, body))


@app.put("/v1/prestadores/{prestador_id}/areas-atendimento")
def definir_areas(prestador_id: str, body: commands.DefinirAreasAtendimento,
                  x_user_id: str | None = Header(None), x_user_role: str | None = Header(None)):
    autorizar_escrita(prestador_id, x_user_id, x_user_role)
    with Session(write_engine()) as s:
        return commands.representar(commands.definir_areas(s, prestador_id, body))


@app.delete("/v1/prestadores/{prestador_id}", status_code=204)
def desativar(prestador_id: str, x_user_id: str | None = Header(None), x_user_role: str | None = Header(None)):
    autorizar_escrita(prestador_id, x_user_id, x_user_role)
    with Session(write_engine()) as s:
        commands.desativar(s, prestador_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ consultas (Read DB + Redis)
@app.get("/v1/prestadores")
def buscar(response: Response, cidade: str | None = None, categoria: str | None = None,
           page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50)):
    result, hit = queries.buscar(cidade, categoria, page, size)
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
    return result


@app.get("/v1/prestadores/{prestador_id}")
def detalhar(prestador_id: str, response: Response):
    doc, hit = queries.detalhar(prestador_id)
    if doc is None:
        raise ApiError(404, "Not Found", f"Prestador {prestador_id} não encontrado.")
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
    return doc


@app.get("/v1/categorias")
def categorias():
    return {"items": commands.CATEGORIAS}
