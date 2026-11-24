"""Executar dentro da internal_net, por exemplo via docker compose exec (ver guia)."""
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

SOL = "http://ms-solicitacoes:8000"
AGENDA = "http://ms-agendamentos:8000"
PAG = "http://ms-pagamentos:8000"
HEADERS = {"X-User-Id": "contratante_15", "X-User-Role": "contratante"}
PRO = {"X-User-Id": "prest_17", "X-User-Role": "prestador"}


def run():
    # Mesma vaga: a segunda contratação comprova a liberação da primeira.
    slot = datetime.now(timezone.utc) + timedelta(days=2)
    with httpx.Client(timeout=3) as client:
        def request(method, base, path, **kwargs):
            response = client.request(method, base + path, **kwargs)
            response.raise_for_status()
            return response.json()

        for token, expected in (("pm_tok_recusado", "COMPENSADA"), ("pm_tok_ok", "CONCLUIDA")):
            cid = "demo-" + uuid4().hex
            headers = {**HEADERS, "X-Correlation-Id": cid}
            sol = request("POST", SOL, "/v1/solicitacoes", headers=headers, json={
                "categoria": "eletrica", "descricao": "Troca de chuveiro - demo Frente 2",
                "endereco": {"cep": "37200000", "cidade": "Lavras", "uf": "MG"}})
            sid = sol["id"]
            quote = request("POST", SOL, f"/v1/solicitacoes/{sid}/orcamentos", headers=PRO, json={
                "valor": {"centavos": 15000, "moeda": "BRL"},
                "descricaoServico": "Trocar chuveiro", "prazoEstimadoDias": 2})
            approval_headers = {**headers, "Idempotency-Key": cid}
            body = {"horarioEscolhido": slot.isoformat(), "meioPagamentoId": token}
            path = f"/v1/orcamentos/{quote['id']}/aprovacao"
            accepted = request("POST", SOL, path, headers=approval_headers, json=body)
            replay = request("POST", SOL, path, headers=approval_headers, json=body)
            assert accepted["sagaId"] == replay["sagaId"], "Idempotência violada"
            print(json.dumps({"token": token, "aceite": accepted}, ensure_ascii=False), flush=True)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                state = request("GET", SOL, f"/v1/solicitacoes/{sid}", headers=headers)
                if state["saga"]["status"] in ("CONCLUIDA", "COMPENSADA"):
                    break
                time.sleep(1)
            assert state["saga"]["status"] == expected, state
            agenda = request("GET", AGENDA, "/v1/agendamentos", params={"solicitacao_id": sid})
            payment = request("GET", PAG, f"/v1/pagamentos/por-saga/{accepted['sagaId']}")
            assert len(agenda["items"]) == (1 if expected == "CONCLUIDA" else 0)
            assert payment["status"] == ("APROVADO" if expected == "CONCLUIDA" else "RECUSADO")
            print(json.dumps({"solicitacao": state, "agenda": agenda, "pagamento": payment},
                             ensure_ascii=False, indent=2), flush=True)
    print("OK: recusa compensada, vaga reutilizada e pagamento aprovado; idempotência verificada.")


if __name__ == "__main__":
    run()
