# PROJECT_STATE — checklist vivo

Legenda: `[x]` pronto · `[ ]` pendente. Atualize ao concluir cada item (arquivos/rotas criados).

## Integrante 1 — Marcus (fundação, gateway, BFFs, K8s)
- [x] Fundação do repo: `.ai-memory/` (ARCHITECTURE, PROJECT_STATE, DECISIONS_LOG)
- [x] Instruções de agente: `.github/copilot-instructions.md`, `.cursorrules`
- [x] `services/_template-fastapi/` (requirements, Dockerfile multi-stage, `app/config.py`, `app/database.py`, `app/main.py` com `/health`, `X-Correlation-Id`, RFC 7807)
- [x] `docker-compose.yml` (redes `edge_net`/`internal_net`, volumes nomeados, kong, rabbitmq, redis, 6× postgres com healthcheck)
- [x] `.env.example` + `.gitignore` (ignora `.env`)
- [x] `gateway/kong.yml` completo: consumers `contratante_15`/`prest_17` (JWT HS256 + ACL), plugins `jwt`/`acl` por serviço, rate limit por rota (10/h criar solicitação, 30/h criar orçamento, 120/min demais) em Redis, `correlation-id`, `cors`
- [x] `scripts/generate_jwt.py` (tokens de teste, só stdlib), `scripts/sync-kong-configmap.sh` (kong.yml -> `k8s/01-kong-config.yaml`)
- [x] `bff-contratante` (`services/bff-contratante`): `GET /health`, `GET /prestadores`, `POST /solicitacoes`, `GET /solicitacoes/{id}/orcamentos`, `POST /orcamentos/{id}/aprovacao`
- [x] `bff-prestador` (`services/bff-prestador`): `GET /health`, `GET /tarefas/{id}`, `POST /solicitacoes/{id}/orcamentos`
- [x] Compose: `bff-contratante` e `bff-prestador` em `internal_net`; Kong depende deles saudáveis
- [x] K8s completo: `00-namespace`, `01-configmap`, `01-kong-config` (gerado), `02-secret`, `03-infra` (Redis, RabbitMQ, 6× Postgres), `04-apps` (BFFs x2, Kong x1), `05-ingress` (via Kong), `k8s/README.md` (guia + demo de escalabilidade)
- [x] K8s: validado em cluster **kind** v1.31 (Pods, Ingress, rotas e demo de escalabilidade). HPA: não feito (opcional)

## Integrante 2 — SAGA, agendamentos, pagamentos
- [x] `ms-solicitacoes` (Orquestrador SAGA persistido + HATEOAS, `POST /v1/orcamentos/{id}/aprovacao` → 202; idempotência, inbox e retomada com backoff)
- [x] `ms-agendamentos` (reserva sem sobreposição + confirmação + `LiberarReserva` idempotente)
- [x] `ms-pagamentos` (Transactional Outbox + Relay Worker `asyncio` com publisher confirms + gatilhos de falha + conciliação/estorno simulado)
- [x] Dockerfiles + entradas Compose + `k8s/06-ms-{solicitacoes,agendamentos,pagamentos}.yaml`
- [x] Testes locais em `services/tests-frente2/`: **17 passaram** (Python 3.14, SQLite, HTTP/AMQP simulados; inclui contratos dos YAMLs). Compilação Python verificada. Roteiro `scripts/demo-frente2.py`; guia `docs/05-frente2-execucao.md`
- [ ] Validar Frente 2 com PostgreSQL/RabbitMQ reais e aplicar seus manifests em cluster (Docker indisponível no ambiente da implementação; testes locais usam SQLite e transportes simulados)

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
- [x] Compose de infraestrutura base + BFFs
- [x] Manifests K8s completos para gateway/BFFs/infra (testados em kind)
- [ ] Compose e K8s dos `ms-*` e `web-*` (cada integrante adiciona os seus)
### Parte 4 — Microsserviços, SAGA, CQRS, RAG, Frontends
- [ ] Microsserviços · [ ] SAGA · [ ] CQRS · [ ] RAG/LangChain · [ ] Frontends

## Endpoints reais implementados
- Frente 2: solicitações/orçamentos/aceite/recusa/consulta com HATEOAS; reserva/confirmação/liberação e consulta de agendamentos; pagamento/conciliação/estorno/repasses; `/health` e `/ready` nos três. Contratos completos em `docs/05-frente2-execucao.md` e decisões 29–36.
- Template: `GET /health` (cada serviço derivado herda).
- `bff-contratante` (via Kong: prefixo `/v1/contratante`): `GET /health`, `GET /prestadores`, `POST /solicitacoes`, `GET /solicitacoes/{id}/orcamentos`, `POST /orcamentos/{id}/aprovacao`
- `bff-prestador` (via Kong: prefixo `/v1/prestador`): `GET /health`, `GET /tarefas/{id}`, `POST /solicitacoes/{id}/orcamentos`

## Pendências conhecidas
- `docs/02`, `03` e `04` já estão no repo e foram incorporadas à `ARCHITECTURE.md` (2026-11-17).
- Divergências docs × implementação: JWT/ACL e rate limit por rota foram implementados (itens 11–12 do log estão resolvidos, ver 17). Segue o item 10 (Elasticsearch × Postgres).
- Auth resolvida para o MVP: JWT com consumers de teste no Kong (ver `DECISIONS_LOG.md` 17). Sem emissor/`POST /auth/*` real.
- **Como integrar seu `ms-*` aos BFFs:** ver `DECISIONS_LOG.md` itens 18–20 (headers, `ENABLE_UPSTREAM_MOCK` e rotas esperadas).
