"""ms-avaliacoes — registra avaliações e publica `AvaliacaoRegistrada` (Transactional Outbox).

O evento já leva `notaMedia` e `totalAvaliacoes` recalculados, então o projetor do ms-prestadores só
copia os valores (idempotente) em vez de somar.
"""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.config import get_settings
from app.database import create_schema, write_engine
from app.http import ApiError, install
from app.messaging import outbox_relay, registrar_evento
from app.models import Avaliacao, ReputacaoPrestador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")
settings = get_settings()

SEED = [  # (solicitacao, prestador, contratante, nota, comentario)
    ("sol_seed_01", "prest_17", "contratante_15", 5, "Resolveu o disjuntor rapidinho."),
    ("sol_seed_02", "prest_17", "contratante_21", 5, "Muito educado e pontual."),
    ("sol_seed_03", "prest_17", "contratante_22", 4, "Bom serviço, atrasou um pouco."),
    ("sol_seed_04", "prest_23", "contratante_15", 5, "Excelente, explicou tudo."),
    ("sol_seed_05", "prest_23", "contratante_30", 5, None),
    ("sol_seed_06", "prest_31", "contratante_31", 4, "Vazamento resolvido."),
    ("sol_seed_07", "prest_32", "contratante_32", 5, "Trocou o registro e revisou o gás."),
    ("sol_seed_08", "prest_41", "contratante_33", 3, "Demorou para chegar."),
    ("sol_seed_09", "prest_52", "contratante_34", 5, "Avaliou a rachadura com cuidado."),
    ("sol_seed_10", "prest_74", "contratante_35", 5, "Chegou em 20 minutos."),
]


class AvaliacaoIn(BaseModel):
    prestadorId: str = Field(min_length=3)
    nota: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


def representar(a: Avaliacao) -> dict:
    return {
        "id": a.id, "solicitacaoId": a.solicitacao_id, "prestadorId": a.prestador_id,
        "contratanteId": a.contratante_id, "nota": a.nota, "comentario": a.comentario,
        "criadaEm": a.criada_em.isoformat(),
        "_links": {
            "self": {"href": f"/v1/avaliacoes/{a.id}", "method": "GET"},
            "prestador": {"href": f"/v1/prestadores/{a.prestador_id}", "method": "GET"},
            "solicitacao": {"href": f"/v1/solicitacoes/{a.solicitacao_id}", "method": "GET"},
        },
    }


def registrar(s: Session, solicitacao_id: str, contratante_id: str, body: AvaliacaoIn) -> Avaliacao:
    """Uma transação: avaliação + reputação (travada) + evento na outbox."""
    try:
        a = Avaliacao(id=f"aval_{uuid.uuid4().hex[:10]}", solicitacao_id=solicitacao_id,
                      prestador_id=body.prestadorId, contratante_id=contratante_id,
                      nota=body.nota, comentario=body.comentario)
        s.add(a)
        s.flush()  # dispara o UNIQUE(solicitacao_id) já aqui

        s.execute(insert(ReputacaoPrestador).values(prestador_id=body.prestadorId, soma_notas=0, total=0)
               .on_conflict_do_nothing(index_elements=["prestador_id"]))
        rep = s.get(ReputacaoPrestador, body.prestadorId, with_for_update=True)
        rep.soma_notas += body.nota
        rep.total += 1
        s.add(rep)

        registrar_evento(s, "AvaliacaoRegistrada", body.prestadorId, rep.total, {
            "avaliacaoId": a.id, "solicitacaoId": solicitacao_id, "prestadorId": body.prestadorId,
            "contratanteId": contratante_id, "nota": body.nota,
            "notaMedia": round(rep.soma_notas / rep.total, 2), "totalAvaliacoes": rep.total,
        })
        s.commit()
    except IntegrityError as exc:
        s.rollback()
        raise ApiError(409, "Conflict", f"A solicitação {solicitacao_id} já foi avaliada.",
                       "https://api.resolvelar.com.br/erros/avaliacao-duplicada") from exc
    s.refresh(a)
    return a


def seed() -> None:
    with Session(write_engine()) as s:
        if s.exec(select(Avaliacao.id).limit(1)).first():
            return
        for sol, prest, contr, nota, coment in SEED:
            registrar(s, sol, contr, AvaliacaoIn(prestadorId=prest, nota=nota, comentario=coment))
    logger.info("Seed: %s avaliações registradas", len(SEED))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(create_schema)
    if settings.SEED_DEMO_DATA:
        await asyncio.to_thread(seed)
    relay = asyncio.create_task(outbox_relay(), name="outbox-relay")
    yield
    relay.cancel()
    await asyncio.gather(relay, return_exceptions=True)


app = FastAPI(title="ms-avaliacoes", version="1.0.0", lifespan=lifespan)
install(app)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.post("/v1/solicitacoes/{solicitacao_id}/avaliacao", status_code=201)
def avaliar(solicitacao_id: str, body: AvaliacaoIn, response: Response,
            x_user_id: str | None = Header(None), x_user_role: str | None = Header(None)):
    """docs/04 1.2: cliente avalia o serviço concluído (201; 403, 409, 422).

    Obs.: a checagem "solicitação CONCLUIDA e pertence ao contratante" depende do ms-solicitacoes
    (Frente 2); por enquanto o prestadorId vem no corpo.
    """
    if not x_user_id:
        raise ApiError(401, "Unauthorized", "Identidade ausente (X-User-Id).")
    if x_user_role and x_user_role != "contratante":
        raise ApiError(403, "Forbidden", "Somente o contratante pode avaliar o serviço.")
    with Session(write_engine()) as s:
        a = registrar(s, solicitacao_id, x_user_id, body)
    response.headers["Location"] = f"/v1/avaliacoes/{a.id}"
    return representar(a)


@app.get("/v1/avaliacoes/{avaliacao_id}")
def detalhar(avaliacao_id: str):
    with Session(write_engine()) as s:
        a = s.get(Avaliacao, avaliacao_id)
    if not a:
        raise ApiError(404, "Not Found", f"Avaliação {avaliacao_id} não encontrada.")
    return representar(a)


@app.get("/v1/avaliacoes")
def listar(prestador_id: str = Query(..., alias="prestador_id"), page: int = Query(1, ge=1),
           size: int = Query(20, ge=1, le=50)):
    with Session(write_engine()) as s:
        filtro = Avaliacao.prestador_id == prestador_id
        total = s.exec(select(func.count()).select_from(Avaliacao).where(filtro)).one()
        itens = s.exec(select(Avaliacao).where(filtro).order_by(col(Avaliacao.criada_em).desc())
                       .offset((page - 1) * size).limit(size)).all()
        rep = s.get(ReputacaoPrestador, prestador_id)
    return {
        "items": [representar(a) for a in itens], "page": page, "size": size, "total": total,
        "resumo": {"prestadorId": prestador_id, "totalAvaliacoes": rep.total if rep else 0,
                   "notaMedia": round(rep.soma_notas / rep.total, 2) if rep and rep.total else None},
    }
