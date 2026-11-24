from datetime import datetime

from fastapi import HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field as InputField, model_validator
from sqlmodel import Field, Session, SQLModel, select

from app.core import create_app, engine, lock, require, uid


class Reserva(SQLModel, table=True):
    id: str = Field(primary_key=True)
    sagaId: str = Field(unique=True, index=True)
    solicitacaoId: str = Field(index=True)
    prestadorId: str = Field(index=True)
    inicio: str
    fim: str
    status: str = "RESERVADA"


class ReservaIn(BaseModel):
    sagaId: str = InputField(min_length=1)
    solicitacaoId: str = InputField(min_length=1)
    prestadorId: str = InputField(min_length=1)
    inicio: AwareDatetime
    fim: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.fim <= self.inicio:
            raise ValueError("fim deve ser posterior ao início")
        return self


app = create_app("ms-agendamentos")


def output(row):
    return {**row.model_dump(), "reservaId": row.id}


@app.post("/v1/reservas", status_code=201)
def reservar(body: ReservaIn):
    with Session(engine) as session, session.begin():
        lock(session, "saga:" + body.sagaId)
        existing = session.exec(select(Reserva).where(Reserva.sagaId == body.sagaId)).first()
        if existing:
            if (existing.solicitacaoId != body.solicitacaoId or existing.prestadorId != body.prestadorId
                    or datetime.fromisoformat(existing.inicio) != body.inicio
                    or datetime.fromisoformat(existing.fim) != body.fim):
                raise HTTPException(409, "sagaId reutilizado com outra reserva")
            return output(existing)
        lock(session, "prestador:" + body.prestadorId)
        active = session.exec(select(Reserva).where(Reserva.prestadorId == body.prestadorId,
                                                   Reserva.status != "LIBERADA")).all()
        if any(datetime.fromisoformat(r.inicio) < body.fim and
               datetime.fromisoformat(r.fim) > body.inicio for r in active):
            raise HTTPException(409, "Horário indisponível")
        row = Reserva(id=uid("res"), **body.model_dump(mode="json"))
        session.add(row)
        return output(row)


def transition(reserva_id, target):
    with Session(engine) as session, session.begin():
        lock(session, "reserva:" + reserva_id)
        row = require(session, Reserva, reserva_id)
        lock(session, "prestador:" + row.prestadorId)
        if row.status == "LIBERADA" and target == "CONFIRMADA":
            raise HTTPException(409, "Reserva já liberada")
        row.status = target
        session.add(row)
        return output(row)


@app.post("/v1/reservas/{reserva_id}/confirmacao")
def confirmar(reserva_id: str):
    return transition(reserva_id, "CONFIRMADA")


@app.post("/v1/reservas/{reserva_id}/liberacao")
def liberar_reserva(reserva_id: str):
    """Compensação LiberarReserva; repetição é segura."""
    return transition(reserva_id, "LIBERADA")


@app.get("/v1/agendamentos")
def listar(request: Request, solicitacao_id: str | None = None, prestador_id: str | None = None,
           de: str | None = None, ate: str | None = None):
    """Por `solicitacao_id` (detalhe da tarefa) ou por `prestador_id` (agenda do profissional, com janela
    opcional `de`/`ate` em ISO-8601). Reservas liberadas não contam. O prestador só vê a própria agenda."""
    if not solicitacao_id and not prestador_id:
        raise HTTPException(422, "Informe solicitacao_id ou prestador_id")
    if prestador_id:
        user = request.headers.get("X-User-Id")
        if user and request.headers.get("X-User-Role") == "prestador" and user != prestador_id:
            raise HTTPException(403, "Só é possível consultar a própria agenda")
    with Session(engine) as session:
        stmt = select(Reserva).where(Reserva.status != "LIBERADA")
        if solicitacao_id:
            stmt = stmt.where(Reserva.solicitacaoId == solicitacao_id)
        if prestador_id:
            stmt = stmt.where(Reserva.prestadorId == prestador_id)
        if de:
            stmt = stmt.where(Reserva.fim >= de)
        if ate:
            stmt = stmt.where(Reserva.inicio <= ate)
        rows = session.exec(stmt.order_by(Reserva.inicio)).all()
        return {"items": [output(row) for row in rows]}
