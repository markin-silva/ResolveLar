from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_deployment_contracts():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    secret = yaml.safe_load((ROOT / "k8s/02-secret.yaml").read_text(encoding="utf-8"))
    for domain in ("solicitacoes", "agendamentos", "pagamentos"):
        name = "ms-" + domain
        service = compose["services"][name]
        assert service["networks"] == ["internal_net"] and "ports" not in service
        assert service["environment"]["DATABASE_URL"] == "${DATABASE_URL_" + domain.upper() + "}"
        deployment, cluster_service = list(yaml.safe_load_all(
            (ROOT / f"k8s/06-{name}.yaml").read_text(encoding="utf-8-sig")))
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert cluster_service["spec"]["selector"] == deployment["spec"]["selector"]["matchLabels"]
        assert container["readinessProbe"]["httpGet"]["path"] == "/ready"
        for env in container["env"]:
            if "valueFrom" in env:
                assert env["valueFrom"]["secretKeyRef"]["key"] in secret["data"]
        assert container["image"] == service["image"]
