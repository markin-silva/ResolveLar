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
- [x] `web-contratante` (triagem IA, busca de prestadores, comparação de orçamentos, aprovação com cartões de teste aprovado/recusado e visualização da resposta da API)
- [x] `web-prestador` (consulta de tarefa e envio de orçamento)
- [x] Dockerfiles multi-stage Nginx + serviços no Compose; manifests K8s dispensados por orientação do professor

## Por etapa
### Parte 3 — Docker & Kubernetes
- [x] Compose de infraestrutura base + BFFs
- [x] Manifests K8s completos para gateway/BFFs/infra (testados em kind)
- [x] Compose dos `web-*`; manifests K8s dos frontends dispensados por orientação do professor
### Parte 4 — Microsserviços, SAGA, CQRS, RAG, Frontends
- [ ] Microsserviços · [ ] SAGA · [ ] CQRS · [ ] RAG/LangChain · [x] Frontends (a integração real depende dos endpoints das demais frentes)

## Endpoints reais implementados
- Template: `GET /health` (cada serviço derivado herda).
- `bff-contratante` (via Kong: prefixo `/v1/contratante`): `GET /health`, `GET /prestadores`, `POST /solicitacoes`, `GET /solicitacoes/{id}/orcamentos`, `POST /orcamentos/{id}/aprovacao`
- `bff-prestador` (via Kong: prefixo `/v1/prestador`): `GET /health`, `GET /tarefas/{id}`, `POST /solicitacoes/{id}/orcamentos`

## Pendências conhecidas
- `docs/02`, `03` e `04` já estão no repo e foram incorporadas à `ARCHITECTURE.md` (2026-11-17).
- Divergências docs × implementação: JWT/ACL e rate limit por rota foram implementados (itens 11–12 do log estão resolvidos, ver 17). Segue o item 10 (Elasticsearch × Postgres).
- Auth resolvida para o MVP: JWT com consumers de teste no Kong (ver `DECISIONS_LOG.md` 17). Sem emissor/`POST /auth/*` real.
- **Como integrar seu `ms-*` aos BFFs:** ver `DECISIONS_LOG.md` itens 18–20 (headers, `ENABLE_UPSTREAM_MOCK` e rotas esperadas).
- **Frontends (branch `feat/web-contratante-prestador`):** apps separados em `clients/web-contratante` (porta 3000) e `clients/web-prestador` (porta 3001), servidos por Nginx e roteando `/v1/` ao Kong. O modo demonstração usa dados identificados como fictícios; modo conectado exige JWT de teste e chama as rotas BFF. A rota de triagem IA prevista no PR #7 e os serviços reais precisam estar integrados/ativos para validar o fluxo ponta a ponta.
