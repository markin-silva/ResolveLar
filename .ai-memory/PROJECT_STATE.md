# PROJECT_STATE — checklist vivo

Legenda: `[x]` pronto · `[ ]` pendente. Atualize ao concluir cada item (arquivos/rotas criados).

## Integrante 1 — Marcus (fundação, gateway, BFFs, K8s)
- [x] Fundação do repo: `.ai-memory/` (ARCHITECTURE, PROJECT_STATE, DECISIONS_LOG)
- [x] Instruções de agente: `.github/copilot-instructions.md`, `.cursorrules`
- [x] `services/_template-fastapi/` (requirements, Dockerfile multi-stage, `app/config.py`, `app/database.py`, `app/main.py` com `/health`, `X-Correlation-Id`, RFC 7807)
- [x] `docker-compose.yml` (redes `edge_net`/`internal_net`, volumes nomeados, kong, rabbitmq, redis, 6× postgres com healthcheck)
- [x] `.env.example` + `.gitignore` (ignora `.env`)
- [x] `gateway/kong.yml` (rotas, correlation-id, cors, rate-limiting/redis)
- [x] Esqueleto `k8s/`: `00-namespace`, `01-configmap`, `02-secret`, `03-infra` (RabbitMQ, Redis), `04-ingress`
- [ ] `bff-contratante`
- [ ] `bff-prestador`
- [ ] K8s: Deployments/Services dos BFFs, escalabilidade (HPA), Postgres no cluster

## Integrante 2 — SAGA, agendamentos, pagamentos
- [ ] `ms-solicitacoes` (Orquestrador SAGA + HATEOAS, `POST /v1/orcamentos/{id}/aprovacao` → 202)
- [ ] `ms-agendamentos` (reserva + `LiberarReserva`)
- [ ] `ms-pagamentos` (Transactional Outbox + Relay Worker `asyncio` + gatilho de falha)
- [ ] Dockerfiles + K8s desses serviços

## Integrante 3 — Prestadores, avaliações, IA
- [ ] `ms-prestadores` (CQRS Write/Read DBs + consumer RabbitMQ)
- [ ] `ms-avaliacoes` (publica `AvaliacaoRegistrada`)
- [ ] Triagem IA: RAG ChromaDB + LangChain chain/tool + resiliência (timeout, retry, cache Redis, fallback)
- [ ] Script de avaliação (5 perguntas com/sem RAG, latência e custo)
- [ ] Dockerfiles + K8s desses serviços

## Integrante 4 — Frontends
- [ ] `web-contratante` (triagem IA, busca CQRS, comparação de orçamentos, aprovação com cartão válido e recusado mostrando compensação da SAGA)
- [ ] `web-prestador`
- [ ] Dockerfiles multi-stage Nginx + K8s

## Por etapa
### Parte 3 — Docker & Kubernetes
- [x] Compose de infraestrutura base e esqueleto `k8s/`
- [ ] Compose com todos os serviços de aplicação
- [ ] Manifests K8s completos (apps, HPA)
### Parte 4 — Microsserviços, SAGA, CQRS, RAG, Frontends
- [ ] Microsserviços · [ ] SAGA · [ ] CQRS · [ ] RAG/LangChain · [ ] Frontends

## Endpoints reais implementados
- Template: `GET /health` (cada serviço derivado herda).

## Pendências conhecidas
- `docs/02`, `03` e `04` já estão no repo e foram incorporadas à `ARCHITECTURE.md` (2026-11-17). `README.md` ainda linka `arquitetura.md`, inexistente (apontar para `docs/`).
- Divergências docs × implementação (JWT/ACL, rate limit por rota, Elasticsearch × Postgres): ver `DECISIONS_LOG.md` itens 10–12.
- Decidir: auth mínima no MVP (emissor JWT) ou identidade simulada. Afeta Kong e BFFs (Integrante 1).
