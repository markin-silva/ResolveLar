"""Chamadas HTTP aos participantes da SAGA. Todos os comandos são idempotentes do lado de quem recebe."""
import os

import httpx

SOLICITACOES = os.getenv("MS_SOLICITACOES_URL", "http://ms-solicitacoes:8000")
AGENDA = os.getenv("MS_AGENDAMENTOS_URL", "http://ms-agendamentos:8000")
PAGAMENTOS = os.getenv("MS_PAGAMENTOS_URL", "http://ms-pagamentos:8000")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "3"))


def client(correlation_id, extra_headers=None):
    return httpx.Client(timeout=TIMEOUT, headers={"X-Correlation-Id": correlation_id, **(extra_headers or {})})


def call(client, method, base, path, body=None):
    response = client.request(method, base + path, json=body)
    response.raise_for_status()
    return response.json()


def detail(exc):
    """Mensagem RFC 7807 do participante, para repassar ao cliente."""
    try:
        return exc.response.json().get("detail") or exc.response.json().get("title")
    except ValueError:
        return None
