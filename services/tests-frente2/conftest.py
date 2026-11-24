"""Quatro apps/bancos isolados (3 participantes + orquestrador); transporte HTTP real dos handlers,
broker simulado."""
import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

SERVICES = Path(__file__).resolve().parents[1]
# chave -> pasta do serviço (o host da URL interna é o próprio nome da pasta)
APPS = {"agendamentos": "ms-agendamentos", "pagamentos": "ms-pagamentos",
        "solicitacoes": "ms-solicitacoes", "orquestrador": "orquestrador-saga"}
HOSTS = {folder: key for key, folder in APPS.items()}


@pytest.fixture(scope="session")
def apps(tmp_path_factory):
    result = {}
    for key, folder in APPS.items():
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
        directory = tmp_path_factory.mktemp(key)
        os.environ["DATABASE_URL"] = "sqlite:///" + (directory / "test.db").as_posix()
        sys.path.insert(0, str(SERVICES / folder))
        main = importlib.import_module("app.main")
        core = importlib.import_module("app.core")
        models = importlib.import_module("app.models") if key in ("solicitacoes", "orquestrador") else main
        worker = importlib.import_module("app.worker") if key == "orquestrador" else None
        participantes = importlib.import_module("app.participantes") if key == "orquestrador" else None
        sys.path.pop(0)
        result[key] = SimpleNamespace(main=main, core=core, models=models, worker=worker,
                                      participantes=participantes, client=TestClient(main.app))
    yield result
    for app in result.values():
        app.client.close()
        app.core.engine.dispose()


@pytest.fixture
def system(apps, monkeypatch):
    for app in apps.values():
        SQLModel.metadata.drop_all(app.core.engine)
        SQLModel.metadata.create_all(app.core.engine)
    original_client = httpx.Client

    def dispatch(request):
        key = HOSTS[request.url.host]
        response = apps[key].client.request(request.method, request.url.raw_path.decode(),
                                            content=request.content, headers=dict(request.headers))
        return httpx.Response(response.status_code, content=response.content,
                              headers=response.headers, request=request)

    transport = httpx.MockTransport(dispatch)
    monkeypatch.setattr(apps["orquestrador"].participantes.httpx, "Client",
                        lambda **kwargs: original_client(transport=transport, **kwargs))
    return apps
