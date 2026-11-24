import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import event
from sqlmodel import Session, select

CONTRATANTE = {"X-User-Id": "contratante_15", "X-User-Role": "contratante", "X-Correlation-Id": "demo-corr"}
PRESTADOR = {"X-User-Id": "prest_17", "X-User-Role": "prestador"}


def setup_saga(system, token="pm_tok_ok", amount=10000, key="attempt-1"):
    client = system["solicitacoes"].client
    sol = client.post("/v1/solicitacoes", headers=CONTRATANTE, json={
        "categoria": "eletrica", "descricao": "Trocar chuveiro",
        "endereco": {"cep": "37200000", "cidade": "Lavras", "uf": "MG"}})
    assert sol.status_code == 201, sol.text
    sid = sol.json()["id"]
    quote = client.post(f"/v1/solicitacoes/{sid}/orcamentos", headers=PRESTADOR, json={
        "valor": {"centavos": amount}, "descricaoServico": "Troca do chuveiro", "prazoEstimadoDias": 2})
    assert quote.status_code == 201, quote.text
    qid = quote.json()["id"]
    body = {"horarioEscolhido": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "meioPagamentoId": token}
    headers = {**CONTRATANTE, "Idempotency-Key": key}
    response = client.post(f"/v1/orcamentos/{qid}/aprovacao", headers=headers, json=body)
    assert response.status_code == 202, response.text
    return sid, qid, response.json()["sagaId"], body, headers


def rows(app, model):
    with Session(app.core.engine) as session:
        return list(session.exec(select(model)).all())


def deliver(system):
    payment = system["pagamentos"]
    worker = system["solicitacoes"].worker
    for row in rows(payment, payment.models.Outbox):
        worker.record_event(worker.PaymentEvent.model_validate(row.payload))


def state(system, sid):
    return system["solicitacoes"].client.get(f"/v1/solicitacoes/{sid}", headers=CONTRATANTE).json()


@pytest.mark.parametrize("token,amount,expected,reservation", [
    ("pm_tok_ok", 10000, "CONFIRMADA", "CONFIRMADA"),
    ("pm_tok_recusado", 10000, "AGUARDANDO_ACEITE", "LIBERADA"),
    ("pm_tok_ok", 500001, "AGUARDANDO_ACEITE", "LIBERADA"),
    ("pm_tok_ok", 500000, "CONFIRMADA", "CONFIRMADA"),
])
def test_saga_end_to_end(system, token, amount, expected, reservation):
    sid, qid, _, _, _ = setup_saga(system, token, amount)
    worker = system["solicitacoes"].worker
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    worker.tick()  # reserva
    worker.tick()  # pagamento + outbox, sem confirmação prematura
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    deliver(system)
    deliver(system)  # entrega duplicada
    worker.tick()
    worker.tick()
    assert state(system, sid)["status"] == expected
    agenda = system["agendamentos"]
    assert rows(agenda, agenda.models.Reserva)[0].status == reservation
    assert len(rows(system["solicitacoes"], system["solicitacoes"].models.Inbox)) == 1
    quote = system["solicitacoes"].client.get(f"/v1/orcamentos/{qid}", headers=CONTRATANTE).json()
    assert ("aprovar" in quote["_links"]) == (expected != "CONFIRMADA")


def test_idempotency_and_owner(system):
    sid, qid, saga_id, body, headers = setup_saga(system)
    client = system["solicitacoes"].client
    path = f"/v1/orcamentos/{qid}/aprovacao"
    assert client.post(path, headers=headers, json=body).json()["sagaId"] == saga_id
    changed = {**body, "meioPagamentoId": "other"}
    assert client.post(path, headers=headers, json=changed).status_code == 409
    assert client.post(path, headers={**headers, "Idempotency-Key": "new"}, json=body).status_code == 409
    assert client.post(path, headers={**headers, "X-User-Id": "other"}, json=body).status_code == 403
    assert client.post(path, headers=CONTRATANTE, json=body).status_code == 422
    assert len(rows(system["solicitacoes"], system["solicitacoes"].models.Saga)) == 1


def test_overlap_and_release(system):
    client = system["agendamentos"].client
    body = {"sagaId": "s1", "solicitacaoId": "sol1", "prestadorId": "p1",
            "inicio": "2030-01-01T14:00:00Z", "fim": "2030-01-01T15:00:00Z"}
    first = client.post("/v1/reservas", json=body)
    rid = first.json()["reservaId"]
    assert client.post("/v1/reservas", json=body).json()["reservaId"] == rid
    assert client.post("/v1/reservas", json={**body, "prestadorId": "p2"}).status_code == 409
    second = {**body, "sagaId": "s2", "inicio": "2030-01-01T14:30:00Z"}
    assert client.post("/v1/reservas", json=second).status_code == 409
    assert client.post(f"/v1/reservas/{rid}/liberacao").status_code == 200
    assert client.post(f"/v1/reservas/{rid}/liberacao").status_code == 200
    assert client.post(f"/v1/reservas/{rid}/confirmacao").status_code == 409
    assert client.post("/v1/reservas", json=second).status_code == 201


def test_payment_atomic_outbox_and_retry(system):
    app = system["pagamentos"]
    body = {"sagaId": "s1", "solicitacaoId": "sol1", "valorCentavos": 12345, "meioPagamentoId": "ok"}
    first = app.client.post("/v1/pagamentos", json=body, headers=CONTRATANTE)
    assert first.status_code == 202
    assert app.client.post("/v1/pagamentos", json=body).json() == first.json()
    assert app.client.post("/v1/pagamentos", json={**body, "valorCentavos": 1}).status_code == 409
    box = rows(app, app.models.Outbox)
    assert len(box) == 1 and box[0].correlationId == "demo-corr"
    assert "meioPagamentoId" not in box[0].payload["dados"]
    repasse = app.client.get("/v1/repasses?solicitacao_id=sol1").json()["items"][0]
    assert repasse["valor_liquido_centavos"] + repasse["taxa_plataforma_centavos"] == 12345
    pid = first.json()["pagamentoId"]
    for _ in range(2):
        assert app.client.post(f"/v1/pagamentos/{pid}/estorno").json()["status"] == "ESTORNADO"
    assert app.client.get("/v1/repasses?solicitacao_id=sol1").json() == {"items": []}


def test_outbox_insert_failure_rolls_back_payment(system):
    app = system["pagamentos"]
    def fail(mapper, connection, target):
        raise RuntimeError("falha no insert da outbox")
    event.listen(app.models.Outbox, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            app.client.post("/v1/pagamentos", json={"sagaId": "s1", "solicitacaoId": "sol1",
                            "valorCentavos": 10, "meioPagamentoId": "ok"})
    finally:
        event.remove(app.models.Outbox, "before_insert", fail)
    assert rows(app, app.models.Pagamento) == []
    assert rows(app, app.models.Outbox) == []


def test_relay_marks_only_after_confirm(system):
    app = system["pagamentos"]
    app.client.post("/v1/pagamentos", json={"sagaId": "s1", "solicitacaoId": "sol1",
                    "valorCentavos": 10, "meioPagamentoId": "ok"})
    class Exchange:
        fail = True
        async def publish(self, message, **kwargs):
            assert message.delivery_mode == 2
            assert kwargs["mandatory"] is True
            if self.fail:
                raise ConnectionError("broker indisponível")
    exchange = Exchange()
    with pytest.raises(ConnectionError):
        asyncio.run(app.main.publish_batch(exchange))
    assert rows(app, app.models.Outbox)[0].publicado is False
    exchange.fail = False
    asyncio.run(app.main.publish_batch(exchange))
    assert rows(app, app.models.Outbox)[0].publicado is True


def retry_now(system):
    app = system["solicitacoes"]
    with Session(app.core.engine) as session, session.begin():
        for saga in session.exec(select(app.models.Saga)).all():
            saga.proximaTentativa = 0
            session.add(saga)


def test_payment_timeout_after_commit_reconciles_without_release(system, monkeypatch):
    sid, _, _, _, _ = setup_saga(system)
    worker = system["solicitacoes"].worker
    worker.tick()
    original = worker.call
    def timeout(client, method, base, path, body=None):
        result = original(client, method, base, path, body)
        if path == "/v1/pagamentos":
            raise httpx.ReadTimeout("resposta perdida após commit")
        return result
    monkeypatch.setattr(worker, "call", timeout)
    worker.tick()
    assert state(system, sid)["saga"]["etapa"] == "PAGAR"
    assert rows(system["agendamentos"], system["agendamentos"].models.Reserva)[0].status == "RESERVADA"
    retry_now(system)
    worker.tick()  # GET por saga encontra cobrança, não envia outro POST
    deliver(system)
    worker.tick()
    worker.tick()
    assert state(system, sid)["status"] == "CONFIRMADA"
    assert len(rows(system["pagamentos"], system["pagamentos"].models.Pagamento)) == 1


def test_compensation_retries_and_can_accept_again(system, monkeypatch):
    sid, qid, _, body, headers = setup_saga(system, "pm_tok_recusado")
    worker = system["solicitacoes"].worker
    worker.tick()
    worker.tick()
    deliver(system)
    worker.tick()
    original = worker.call
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("agenda indisponível")
    monkeypatch.setattr(worker, "call", unavailable)
    worker.tick()
    assert state(system, sid)["saga"]["status"] == "COMPENSACAO_PENDENTE"
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    monkeypatch.setattr(worker, "call", original)
    retry_now(system)
    worker.tick()
    assert state(system, sid)["saga"]["status"] == "COMPENSADA"
    new = system["solicitacoes"].client.post(f"/v1/orcamentos/{qid}/aprovacao",
        headers={**headers, "Idempotency-Key": "attempt-2"}, json={**body, "meioPagamentoId": "ok"})
    assert new.status_code == 202
    worker.tick()
    worker.tick()
    deliver(system)
    worker.tick()
    worker.tick()
    assert state(system, sid)["status"] == "CONFIRMADA"


def test_confirm_failure_refunds_before_release(system):
    sid, _, _, _, _ = setup_saga(system)
    worker = system["solicitacoes"].worker
    worker.tick()
    worker.tick()
    deliver(system)
    worker.tick()
    rid = state(system, sid)["saga"]["reservaId"]
    system["agendamentos"].client.post(f"/v1/reservas/{rid}/liberacao")
    worker.tick()  # confirmar -> 409 -> estornar
    assert state(system, sid)["saga"]["etapa"] == "ESTORNAR"
    worker.tick()
    assert rows(system["pagamentos"], system["pagamentos"].models.Pagamento)[0].status == "ESTORNADO"
    worker.tick()
    assert state(system, sid)["saga"]["status"] == "COMPENSADA"


def test_validation_and_correlation(system):
    client = system["solicitacoes"].client
    response = client.post("/v1/solicitacoes", json={}, headers=CONTRATANTE)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-correlation-id"] == "demo-corr"
    assert set(("type", "title", "status", "detail", "instance")) <= response.json().keys()


def test_schedule_conflict_never_charges(system):
    sid, _, _, body, _ = setup_saga(system)
    start = datetime.fromisoformat(body["horarioEscolhido"])
    system["agendamentos"].client.post("/v1/reservas", json={
        "sagaId": "other", "solicitacaoId": "other", "prestadorId": "prest_17",
        "inicio": start.isoformat(), "fim": (start + timedelta(hours=1)).isoformat()})
    system["solicitacoes"].worker.tick()
    assert state(system, sid)["saga"]["status"] == "COMPENSADA"
    assert rows(system["pagamentos"], system["pagamentos"].models.Pagamento) == []


def test_incompatible_event_does_not_update_saga(system):
    sid, _, saga_id, _, _ = setup_saga(system)
    worker = system["solicitacoes"].worker
    event_data = worker.PaymentEvent.model_validate({"eventId": "invalid", "tipo": "PagamentoAprovado",
        "versaoAgregado": 1, "ocorridoEm": datetime.now(timezone.utc).isoformat(),
        "dados": {"sagaId": saga_id, "solicitacaoId": sid, "pagamentoId": "wrong", "valorCentavos": 1}})
    with pytest.raises(ValueError):
        worker.record_event(event_data)
    assert state(system, sid)["saga"]["pagamentoId"] is None
    assert rows(system["solicitacoes"], system["solicitacoes"].models.Inbox) == []


def test_expired_quote_has_no_approval_link(system):
    _, qid, _, _, _ = setup_saga(system)
    app = system["solicitacoes"]
    with Session(app.core.engine) as session, session.begin():
        quote = session.get(app.models.Orcamento, qid)
        quote.status = "PENDENTE"
        quote.validoAte = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        session.add(quote)
    quote = app.client.get(f"/v1/orcamentos/{qid}", headers=CONTRATANTE).json()
    assert quote["status"] == "EXPIRADO"
    assert "aprovar" not in quote["_links"]
