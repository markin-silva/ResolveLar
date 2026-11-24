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
    # A aprovação vai para o orquestrador (no Docker, o Kong encaminha direto para ele).
    response = system["orquestrador"].client.post(f"/v1/orcamentos/{qid}/aprovacao", headers=headers, json=body)
    assert response.status_code == 202, response.text
    return sid, qid, response.json()["sagaId"], body, headers


def rows(app, model):
    with Session(app.core.engine) as session:
        return list(session.exec(select(model)).all())


def deliver(system):
    payment = system["pagamentos"]
    worker = system["orquestrador"].worker
    for row in rows(payment, payment.models.Outbox):
        worker.record_event(worker.PaymentEvent.model_validate(row.payload))


def ticks(system, n):
    for _ in range(n):
        system["orquestrador"].worker.tick()


def state(system, sid):
    return system["solicitacoes"].client.get(f"/v1/solicitacoes/{sid}", headers=CONTRATANTE).json()


def saga(system, saga_id):
    return system["orquestrador"].client.get(f"/v1/sagas/{saga_id}", headers=CONTRATANTE).json()


@pytest.mark.parametrize("token,amount,expected,reservation", [
    ("pm_tok_ok", 10000, "CONFIRMADA", "CONFIRMADA"),
    ("pm_tok_recusado", 10000, "AGUARDANDO_ACEITE", "LIBERADA"),
    ("pm_tok_ok", 500001, "AGUARDANDO_ACEITE", "LIBERADA"),
    ("pm_tok_ok", 500000, "CONFIRMADA", "CONFIRMADA"),
])
def test_saga_end_to_end(system, token, amount, expected, reservation):
    sid, qid, saga_id, _, _ = setup_saga(system, token, amount)
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    assert state(system, sid)["sagaId"] == saga_id
    ticks(system, 2)  # reserva; pagamento + outbox, sem confirmação prematura
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    deliver(system)
    deliver(system)  # entrega duplicada
    ticks(system, 3)
    assert state(system, sid)["status"] == expected
    assert saga(system, saga_id)["status"] == ("CONCLUIDA" if expected == "CONFIRMADA" else "COMPENSADA")
    agenda = system["agendamentos"]
    assert rows(agenda, agenda.models.Reserva)[0].status == reservation
    assert len(rows(system["orquestrador"], system["orquestrador"].models.Inbox)) == 1
    quote = system["solicitacoes"].client.get(f"/v1/orcamentos/{qid}", headers=CONTRATANTE).json()
    assert ("aprovar" in quote["_links"]) == (expected != "CONFIRMADA")


def test_idempotency_and_owner(system):
    sid, qid, saga_id, body, headers = setup_saga(system)
    client = system["orquestrador"].client
    path = f"/v1/orcamentos/{qid}/aprovacao"
    assert client.post(path, headers=headers, json=body).json()["sagaId"] == saga_id
    changed = {**body, "meioPagamentoId": "other"}
    assert client.post(path, headers=headers, json=changed).status_code == 409
    new_key = {**headers, "Idempotency-Key": "new"}
    assert client.post(path, headers=new_key, json=body).status_code == 409  # solicitação já travada
    assert client.post(path, headers=new_key, json=body).status_code == 409  # replay da rejeição
    other = {**headers, "X-User-Id": "other", "Idempotency-Key": "x"}
    assert client.post(path, headers=other, json=body).status_code == 403
    assert client.post(path, headers=CONTRATANTE, json=body).status_code == 422  # sem Idempotency-Key
    em_andamento = [s for s in rows(system["orquestrador"], system["orquestrador"].models.Saga)
                    if s.status != "REJEITADA"]
    assert [s.id for s in em_andamento] == [saga_id]


def test_solicitacoes_has_no_saga_state(system):
    """O ms-solicitacoes é só domínio: o estado da SAGA vive no orquestrador."""
    models = system["solicitacoes"].models
    assert not hasattr(models, "Saga") and not hasattr(models, "Inbox")
    assert hasattr(system["orquestrador"].models, "Saga")


def test_domain_commands_are_idempotent(system):
    sid, qid, saga_id, _, _ = setup_saga(system)
    client = system["solicitacoes"].client
    base = f"/v1/orcamentos/{qid}/contratacao"
    # iniciar de novo com a mesma SAGA devolve o mesmo resultado; com outra, conflito
    assert client.post(base, headers=CONTRATANTE, json={"sagaId": saga_id}).status_code == 200
    assert client.post(base, headers=CONTRATANTE, json={"sagaId": "outra"}).status_code == 409
    # cancelar com outra SAGA não mexe em nada
    assert client.post(base + "/cancelamento", json={"sagaId": "outra"}).json()["status"] == "EM_CONFIRMACAO"
    for _ in range(2):
        assert client.post(base + "/confirmacao", json={"sagaId": saga_id}).json()["status"] == "CONFIRMADA"
    assert client.post(base + "/cancelamento", json={"sagaId": saga_id}).status_code == 409


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
    app = system["orquestrador"]
    with Session(app.core.engine) as session, session.begin():
        for row in session.exec(select(app.models.Saga)).all():
            row.proximaTentativa = 0
            session.add(row)


def test_payment_timeout_after_commit_reconciles_without_release(system, monkeypatch):
    sid, _, saga_id, _, _ = setup_saga(system)
    participantes = system["orquestrador"].participantes
    ticks(system, 1)
    original = participantes.call
    def timeout(client, method, base, path, body=None):
        result = original(client, method, base, path, body)
        if path == "/v1/pagamentos":
            raise httpx.ReadTimeout("resposta perdida após commit")
        return result
    monkeypatch.setattr(participantes, "call", timeout)
    ticks(system, 1)
    assert saga(system, saga_id)["etapa"] == "PAGAR"
    assert rows(system["agendamentos"], system["agendamentos"].models.Reserva)[0].status == "RESERVADA"
    retry_now(system)
    ticks(system, 1)  # GET por saga encontra cobrança, não envia outro POST
    deliver(system)
    ticks(system, 3)
    assert state(system, sid)["status"] == "CONFIRMADA"
    assert len(rows(system["pagamentos"], system["pagamentos"].models.Pagamento)) == 1


def test_compensation_retries_and_can_accept_again(system, monkeypatch):
    sid, qid, saga_id, body, headers = setup_saga(system, "pm_tok_recusado")
    participantes = system["orquestrador"].participantes
    ticks(system, 2)
    deliver(system)
    ticks(system, 1)  # AGUARDAR_EVENTO -> LIBERAR
    original = participantes.call
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("agenda indisponível")
    monkeypatch.setattr(participantes, "call", unavailable)
    ticks(system, 1)
    assert saga(system, saga_id)["status"] == "COMPENSACAO_PENDENTE"
    assert state(system, sid)["status"] == "EM_CONFIRMACAO"
    monkeypatch.setattr(participantes, "call", original)
    retry_now(system)
    ticks(system, 2)  # LIBERAR -> CANCELAR_SOLICITACAO -> FINALIZADA
    assert saga(system, saga_id)["status"] == "COMPENSADA"
    assert state(system, sid)["status"] == "AGUARDANDO_ACEITE"
    new = system["orquestrador"].client.post(f"/v1/orcamentos/{qid}/aprovacao",
        headers={**headers, "Idempotency-Key": "attempt-2"}, json={**body, "meioPagamentoId": "ok"})
    assert new.status_code == 202, new.text
    ticks(system, 2)
    deliver(system)
    ticks(system, 3)
    assert state(system, sid)["status"] == "CONFIRMADA"


def test_confirm_failure_refunds_before_release(system):
    sid, _, saga_id, _, _ = setup_saga(system)
    ticks(system, 2)
    deliver(system)
    ticks(system, 1)
    rid = saga(system, saga_id)["reservaId"]
    system["agendamentos"].client.post(f"/v1/reservas/{rid}/liberacao")
    ticks(system, 1)  # confirmar reserva -> 409 -> estornar
    assert saga(system, saga_id)["etapa"] == "ESTORNAR"
    ticks(system, 1)
    assert rows(system["pagamentos"], system["pagamentos"].models.Pagamento)[0].status == "ESTORNADO"
    ticks(system, 2)
    assert saga(system, saga_id)["status"] == "COMPENSADA"
    assert state(system, sid)["status"] == "AGUARDANDO_ACEITE"


def test_unavailable_solicitacoes_aborts_without_side_effects(system, monkeypatch):
    client = system["solicitacoes"].client
    sid = client.post("/v1/solicitacoes", headers=CONTRATANTE, json={
        "categoria": "eletrica", "descricao": "Trocar chuveiro",
        "endereco": {"cep": "37200000", "cidade": "Lavras", "uf": "MG"}}).json()["id"]
    qid = client.post(f"/v1/solicitacoes/{sid}/orcamentos", headers=PRESTADOR, json={
        "valor": {"centavos": 100}, "descricaoServico": "Troca", "prazoEstimadoDias": 1}).json()["id"]
    participantes = system["orquestrador"].participantes
    original = participantes.call
    def down(client, method, base, path, body=None):
        if path.endswith("/contratacao"):
            raise httpx.ConnectError("ms-solicitacoes fora")
        return original(client, method, base, path, body)
    monkeypatch.setattr(participantes, "call", down)
    body = {"horarioEscolhido": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "meioPagamentoId": "ok"}
    response = system["orquestrador"].client.post(f"/v1/orcamentos/{qid}/aprovacao",
                                                  headers={**CONTRATANTE, "Idempotency-Key": "k"}, json=body)
    assert response.status_code == 503
    ticks(system, 1)  # ABORTAR: cancelamento idempotente no ms-solicitacoes
    only = rows(system["orquestrador"], system["orquestrador"].models.Saga)[0]
    assert only.status == "ABORTADA"
    assert state(system, sid)["status"] == "AGUARDANDO_ACEITE"
    assert rows(system["agendamentos"], system["agendamentos"].models.Reserva) == []
    assert rows(system["pagamentos"], system["pagamentos"].models.Pagamento) == []


def test_validation_and_correlation(system):
    for key in ("solicitacoes", "orquestrador"):
        client = system[key].client
        path = "/v1/solicitacoes" if key == "solicitacoes" else "/v1/orcamentos/x/aprovacao"
        response = client.post(path, json={}, headers=CONTRATANTE)
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["x-correlation-id"] == "demo-corr"
        assert set(("type", "title", "status", "detail", "instance")) <= response.json().keys()


def test_schedule_conflict_never_charges(system):
    sid, _, saga_id, body, _ = setup_saga(system)
    start = datetime.fromisoformat(body["horarioEscolhido"])
    system["agendamentos"].client.post("/v1/reservas", json={
        "sagaId": "other", "solicitacaoId": "other", "prestadorId": "prest_17",
        "inicio": start.isoformat(), "fim": (start + timedelta(hours=1)).isoformat()})
    ticks(system, 2)  # RESERVAR (409) -> CANCELAR_SOLICITACAO -> FINALIZADA
    assert saga(system, saga_id)["status"] == "COMPENSADA"
    assert state(system, sid)["status"] == "AGUARDANDO_ACEITE"
    assert rows(system["pagamentos"], system["pagamentos"].models.Pagamento) == []


def test_incompatible_event_does_not_update_saga(system):
    sid, _, saga_id, _, _ = setup_saga(system)
    worker = system["orquestrador"].worker
    event_data = worker.PaymentEvent.model_validate({"eventId": "invalid", "tipo": "PagamentoAprovado",
        "versaoAgregado": 1, "ocorridoEm": datetime.now(timezone.utc).isoformat(),
        "dados": {"sagaId": saga_id, "solicitacaoId": sid, "pagamentoId": "wrong", "valorCentavos": 1}})
    with pytest.raises(ValueError):
        worker.record_event(event_data)
    assert saga(system, saga_id)["pagamentoId"] is None
    assert rows(system["orquestrador"], system["orquestrador"].models.Inbox) == []


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
