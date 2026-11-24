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
