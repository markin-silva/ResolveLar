"""Três apps/bancos isolados; transporte HTTP real dos handlers, broker simulado."""
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


@pytest.fixture(scope="session")
def apps(tmp_path_factory):
    result = {}
    for domain in ("agendamentos", "pagamentos", "solicitacoes"):
        for key in list(sys.modules):
            if key == "app" or key.startswith("app."):
                del sys.modules[key]
        directory = tmp_path_factory.mktemp(domain)
        os.environ["DATABASE_URL"] = "sqlite:///" + (directory / "test.db").as_posix()
        sys.path.insert(0, str(SERVICES / ("ms-" + domain)))
        main = importlib.import_module("app.main")
        core = importlib.import_module("app.core")
        models = importlib.import_module("app.models") if domain == "solicitacoes" else main
        worker = importlib.import_module("app.worker") if domain == "solicitacoes" else None
        sys.path.pop(0)
        result[domain] = SimpleNamespace(main=main, core=core, models=models, worker=worker,
                                          client=TestClient(main.app))
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
        domain = request.url.host.removeprefix("ms-")
        response = apps[domain].client.request(request.method, request.url.raw_path.decode(),
                                               content=request.content, headers=dict(request.headers))
        return httpx.Response(response.status_code, content=response.content,
                              headers=response.headers, request=request)

    transport = httpx.MockTransport(dispatch)
    monkeypatch.setattr(apps["solicitacoes"].worker.httpx, "Client",
                        lambda **kwargs: original_client(transport=transport, **kwargs))
    return apps
