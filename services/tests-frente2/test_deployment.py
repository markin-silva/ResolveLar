from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_deployment_contracts():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for domain in ("solicitacoes", "agendamentos", "pagamentos"):
        name = "ms-" + domain
        service = compose["services"][name]
        assert service["networks"] == ["internal_net"] and "ports" not in service
        assert service["environment"]["DATABASE_URL"] == "${DATABASE_URL_" + domain.upper() + "}"
        assert service["image"] == "resolvelar/" + name + ":latest"
    # O ms-solicitacoes é só domínio: não fala com o broker nem com os outros participantes.
    assert "RABBITMQ_URL" not in compose["services"]["ms-solicitacoes"]["environment"]


def test_orchestrator_is_outside_the_domain_services():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    orq = compose["services"]["orquestrador-saga"]
    assert orq["networks"] == ["internal_net"] and "ports" not in orq
    assert "db-orquestrador" in orq["depends_on"]  # banco próprio, só com o estado da SAGA
    assert "orquestrador-saga" in compose["services"]["kong"]["depends_on"]
    kong = yaml.safe_load((ROOT / "gateway/kong.tpl.yml").read_text(encoding="utf-8"))
    service = next(s for s in kong["services"] if s["name"] == "orquestrador-saga")
    route = service["routes"][0]
    assert route["paths"][0].startswith("~/v1/contratante/orcamentos/") and route["methods"] == ["POST"]
    assert {p["name"] for p in service["plugins"]} >= {"jwt", "acl", "pre-function"}
