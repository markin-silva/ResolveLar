# Kubernetes — ResolveLar (Parte 3)

Roda o gateway e os BFFs em um cluster local (kind, Minikube ou Docker Desktop) e demonstra **escalabilidade horizontal**.

> **Estado:** testado em cluster **kind** v1.31 (Linux, x86_64): todos os Pods sobem, o gateway responde pelo Ingress e a demo de escalabilidade distribui as requisições entre os Pods.

## O que sobe

| Arquivo | Conteúdo |
|---|---|
| `00-namespace.yaml` | Namespace `resolvelar` |
| `01-configmap.yaml` | Hosts e URLs internas, `ENABLE_UPSTREAM_MOCK` |
| `01-kong-config.yaml` | `kong.yml` empacotado em ConfigMap (**gerado**, não edite à mão) |
| `02-secret.yaml` | Senhas e chaves de **exemplo** (placeholders) |
| `03-infra.yaml` | Redis, RabbitMQ e 6× PostgreSQL (PVC + Deployment + Service) |
| `04-apps.yaml` | `bff-contratante` ×2, `bff-prestador` ×2, `kong` ×1 |
| `05-ingress.yaml` | Ingress `/v1/contratante` e `/v1/prestador` → Kong |

```
Ingress (nginx) ──► Service kong ──► Pod kong ──► Service bff-* ──► Pods bff-* (2 réplicas)
                     valida JWT/ACL, rate limit (Redis), remove o prefixo
```

O Ingress só entrega o tráfego ao Kong. JWT, ACL, rate limit e `X-Correlation-Id` continuam sendo do Kong, igual ao Docker Compose.

## 0. Pré-requisitos

Docker, `kubectl` e **um** destes: [kind](https://kind.sigs.k8s.io/) ou [Minikube](https://minikube.sigs.k8s.io/). Docker Desktop com Kubernetes ligado também serve.

## 1. Subir o cluster e carregar as imagens

As imagens dos BFFs são locais (não estão em registry). Construa e carregue no cluster:

```bash
# na raiz do repositório
docker build -t resolvelar/bff-contratante:latest services/bff-contratante
docker build -t resolvelar/bff-prestador:latest   services/bff-prestador
```

**Opção A — kind** (o Ingress precisa de portas mapeadas na criação do cluster):

```bash
cat <<'EOF' | kind create cluster --name resolvelar --config -
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - {containerPort: 80, hostPort: 8080, protocol: TCP}
EOF

kind load docker-image resolvelar/bff-contratante:latest resolvelar/bff-prestador:latest --name resolvelar

# ingress-nginx para kind
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s
```
URL de entrada: `http://localhost:8080`.

**Opção B — Minikube:**

```bash
minikube start
minikube addons enable ingress
minikube image load resolvelar/bff-contratante:latest
minikube image load resolvelar/bff-prestador:latest
```
URL de entrada: `http://$(minikube ip)` (no Linux com driver docker, use `minikube tunnel` e `http://127.0.0.1`).

> Docker Desktop: as imagens locais já ficam visíveis ao cluster. Instale o ingress-nginx pelo manifesto "cloud" e use `http://localhost`.

## 2. Aplicar os manifestos

```bash
kubectl apply -f k8s/
kubectl -n resolvelar get pods -w      # aguarde tudo Running/Ready (Ctrl+C para sair)
```

`kubectl apply -f k8s/` aplica os arquivos em ordem alfabética (`00` … `05`), então namespace, ConfigMap e Secret existem antes dos Deployments.

## 3. Validar

```bash
kubectl -n resolvelar get configmap,secret,pvc
kubectl -n resolvelar get deploy,svc,pods -o wide
kubectl -n resolvelar get ingress
kubectl -n resolvelar describe configmap resolvelar-config
kubectl -n resolvelar get secret resolvelar-secrets -o jsonpath='{.data.POSTGRES_USER}' | base64 -d; echo   # resolvelar
```

Esperado: Deployments `bff-contratante` e `bff-prestador` com `2/2`, `kong` com `1/1`, Services `ClusterIP`, Ingress com as duas rotas.

Teste de ponta a ponta (ajuste `URL` conforme a opção escolhida):

```bash
URL=http://localhost:8080
eval "$(python3 scripts/generate_jwt.py | grep export)"

curl -i  $URL/v1/contratante/prestadores                                   # 401 (sem token)
curl -si -H "Authorization: Bearer $TOKEN_CONTRATANTE" $URL/v1/contratante/prestadores | head -20   # 200
curl -si -H "Authorization: Bearer $TOKEN_CONTRATANTE" $URL/v1/prestador/tarefas/sol_8f21 | head -1 # 403 (ACL)
curl -s  -H "Authorization: Bearer $TOKEN_PRESTADOR"   $URL/v1/prestador/tarefas/sol_8f21           # 200
```

Com `ENABLE_UPSTREAM_MOCK=true` as respostas trazem o header `X-Mock-Upstream: true` (dados de exemplo da `docs/02`).

## 4. Demonstração de escalabilidade

```bash
URL=http://localhost:8080
eval "$(python3 scripts/generate_jwt.py | grep export)"

# 1) estado inicial: 2 réplicas
kubectl -n resolvelar get pods -l app=bff-contratante

# 2) escalar para 3
kubectl scale deployment bff-contratante --replicas=3 -n resolvelar
kubectl -n resolvelar rollout status deployment/bff-contratante

# 3) 30 chamadas: o X-Pod-Name alterna entre os 3 Pods
for i in $(seq 1 30); do
  curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN_CONTRATANTE" $URL/v1/contratante/prestadores \
    | grep -i '^x-pod-name'
done | sort | uniq -c
```

Saída esperada (a divisão não precisa ser exata; no nosso teste com 60 chamadas: 11, 9 e 10):

```
     11 x-pod-name: bff-contratante-8674c45788-bnf29
      9 x-pod-name: bff-contratante-8674c45788-qdvjw
     10 x-pod-name: bff-contratante-8674c45788-swzvk
```

Para mostrar autocura, apague um Pod e veja o Kubernetes recriá-lo:

```bash
kubectl -n resolvelar delete pod -l app=bff-contratante --field-selector=status.phase=Running --wait=false | head -1
kubectl -n resolvelar get pods -l app=bff-contratante -w
```

> **Rate limit:** as chamadas passam pelo Kong, que limita 120 req/min por usuário. O loop de 30 chamadas cabe no limite; se rodar várias vezes seguidas, espere 1 minuto ou receberá `429`.

### Problemas que encontramos no primeiro teste (já corrigidos nos manifestos)

| Sintoma | Causa | Correção |
|---|---|---|
| `kong` em `CrashLoopBackOff`, motivo `OOMKilled` | Limite de 512Mi pequeno para o `kong.yml` completo | Limite de 1Gi (`04-apps.yaml`) |
| `rabbitmq` em `0/1` `Ready`, probe com timeout | `rabbitmq-diagnostics ping` demora mais de 1s no primeiro boot | `timeoutSeconds: 10`, `initialDelaySeconds: 30` (`03-infra.yaml`) |
| Todas as 30 requisições no mesmo Pod ao escalar | Keep-alive do Kong com os BFFs: o kube-proxy só escolhe o Pod ao abrir a conexão | `KONG_UPSTREAM_KEEPALIVE_POOL_SIZE=0` e `KONG_UPSTREAM_KEEPALIVE_MAX_REQUESTS=1` (`04-apps.yaml`) |

Se o Kong reiniciar em loop: `kubectl -n resolvelar describe pod -l app=kong` e procure `OOMKilled` em *Last State*. Se o RabbitMQ não ficar `Ready`: `kubectl -n resolvelar logs -l app=rabbitmq --tail=50`.

Custo do keep-alive desligado: cada requisição abre uma conexão nova entre o Kong e o BFF. Para uma demo local é aceitável; em produção, o ideal é manter o reuso e confiar no balanceamento do próprio Service, ou usar um balanceador com afinidade por requisição.

## 5. Quando os microsserviços entrarem no cluster

1. Crie os Deployments/Services dos `ms-*` com os nomes de `.ai-memory/ARCHITECTURE.md` (ex.: `ms-solicitacoes:8000`).
2. Desligue o mock e reinicie os BFFs:
   ```bash
   kubectl -n resolvelar patch configmap resolvelar-config -p '{"data":{"ENABLE_UPSTREAM_MOCK":"false"}}'
   kubectl -n resolvelar rollout restart deployment/bff-contratante deployment/bff-prestador
   ```

## 6. Editou o `gateway/kong.yml`?

O cluster usa uma cópia do arquivo em ConfigMap. Regenere e reinicie o Kong:

```bash
./scripts/sync-kong-configmap.sh
kubectl apply -f k8s/01-kong-config.yaml
kubectl -n resolvelar rollout restart deployment/kong
```

## 7. Limpar

```bash
kubectl delete namespace resolvelar      # remove tudo (inclusive os PVCs)
kind delete cluster --name resolvelar    # ou: minikube delete
```

## Limitações conhecidas

- **Testado só em kind.** Minikube e Docker Desktop não foram testados.
- **Imagens locais:** o `kind load` precisa ser refeito sempre que a imagem do BFF mudar, senão o cluster continua usando a versão antiga (com `:latest` e `IfNotPresent`).
- **Secret de exemplo:** os valores são placeholders em base64 — base64 não é criptografia. Em ambiente real, crie os segredos fora do Git.
- **Bancos e RabbitMQ sem consumidores:** sobem, mas nenhum serviço os usa até os `ms-*` entrarem.
- **Kong com 1 réplica** (a pedido da Parte 3): o rate limit usa Redis, então escalar o Kong não altera a contagem.
- **JWT de teste:** o segredo `resolvelar-jwt-secret-2026` é público no repositório. Serve só para demonstração local.
