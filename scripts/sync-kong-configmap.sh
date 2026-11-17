#!/usr/bin/env bash
# Regenera k8s/01-kong-config.yaml (ConfigMap) a partir de gateway/kong.yml.
# Rode sempre que editar o kong.yml, para o Compose e o Kubernetes usarem a mesma configuração.
set -euo pipefail
cd "$(dirname "$0")/.."

{
  cat <<'EOF'
# GERADO por scripts/sync-kong-configmap.sh a partir de gateway/kong.yml — não edite à mão.
# Contém as credenciais JWT DE TESTE definidas no kong.yml (demo local, sem provedor de identidade).
apiVersion: v1
kind: ConfigMap
metadata:
  name: kong-config
  namespace: resolvelar
data:
  kong.yml: |
EOF
  sed 's/^/    /; s/[[:space:]]*$//' gateway/kong.yml
} > k8s/01-kong-config.yaml

echo "k8s/01-kong-config.yaml atualizado"
