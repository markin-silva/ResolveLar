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
- [x] `ms-prestadores` (`services/ms-prestadores`): CQRS com `db-prestadores-write` (agregado + outbox) e `db-prestadores-read` (`prestador_view` desnormalizada); relay da outbox e projetor RabbitMQ idempotente (eventId + versaoAgregado, retry + DLQ); cache Redis com invalidação pelo projetor; seed de 11 prestadores
- [x] `ms-avaliacoes` (`services/ms-avaliacoes`): `POST /v1/solicitacoes/{id}/avaliacao` + Outbox publicando `AvaliacaoRegistrada` (notaMedia/totalAvaliacoes) → Read DB do `ms-prestadores`; seed de 10 avaliações
- [x] Triagem IA (`services/ms-triagem`, serviço próprio — ver DECISIONS_LOG 29): cadeia LCEL RAG (ChromaDB) → LLM estruturado (Gemini/OpenAI) → `@tool buscar_prestadores` (ms-prestadores real); timeout, retry com backoff, circuit breaker, cache Redis e fallback por regras
- [x] Script de avaliação: `docker compose exec ms-triagem python -m app.avaliacao` (5 perguntas × com/sem RAG, acerto, cobertura, latência, tokens, custo)
- [x] Avaliação com LLM real (Gemini `gemini-3.5-flash-lite`) em `docs/05-avaliacao-triagem.md`: 5/5 categorias e urgências; cobertura de segurança 75% com RAG × 40% sem; ~US$ 0,0007/triagem; latência alta do provedor no dia (p50 ~10s) documentada
- [x] Dockerfiles + Compose desses serviços (K8s fora do escopo)
- Testado em Docker Desktop (Windows, 2026-11-19): busca/triagem/avaliação via Kong com JWT, 409/422/403, cache HIT/MISS, Redis fora, ms-prestadores fora, chave de LLM inválida e Gemini lento (fallback + circuit breaker), cache HIT de resposta do LLM (19s → 0,6ms), primeiro boot com fila ainda não declarada

## Integrante 4 — Frontends
- [ ] `web-contratante` (triagem IA, busca CQRS, comparação de orçamentos, aprovação com cartão válido e recusado mostrando compensação da SAGA)
- [ ] `web-prestador`
- [ ] Dockerfiles multi-stage Nginx + K8s

## Por etapa
### Parte 3 — Docker & Kubernetes
- [x] Compose de infraestrutura base + BFFs
- [x] Manifests K8s completos para gateway/BFFs/infra (testados em kind)
- [ ] Compose dos `ms-*` e `web-*` (cada integrante adiciona os seus; feito: `ms-prestadores`, `ms-avaliacoes`, `ms-triagem`). **Kubernetes saiu do escopo** (DECISIONS_LOG 30)
### Parte 4 — Microsserviços, SAGA, CQRS, RAG, Frontends
- [ ] Microsserviços (3/6) · [ ] SAGA · [x] CQRS · [x] RAG/LangChain · [ ] Frontends

## Endpoints reais implementados
- Template: `GET /health` (cada serviço derivado herda).
- `bff-contratante` (via Kong: prefixo `/v1/contratante`): `GET /health`, `GET /prestadores`, `POST /triagem`, `POST /solicitacoes`, `GET /solicitacoes/{id}/orcamentos`, `POST /solicitacoes/{id}/avaliacao`, `POST /orcamentos/{id}/aprovacao`
- `ms-prestadores`: `POST /v1/prestadores`, `PATCH /v1/prestadores/{id}`, `PUT /v1/prestadores/{id}/areas-atendimento`, `DELETE /v1/prestadores/{id}`, `GET /v1/prestadores?cidade=&categoria=&page=&size=`, `GET /v1/prestadores/{id}`, `GET /v1/categorias`
- `ms-avaliacoes`: `POST /v1/solicitacoes/{id}/avaliacao`, `GET /v1/avaliacoes/{id}`, `GET /v1/avaliacoes?prestador_id=`
- `ms-triagem`: `POST /v1/triagem?rag=&cache=`, `GET /v1/triagem/base-conhecimento?q=`
- Os `ms-*` ficam só na `internal_net` (sem porta no host). Para abrir o `/docs` de um deles: `docker compose exec ms-prestadores python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/openapi.json').read()[:200])"` ou um curl na rede interna: `docker run --rm --network resolvelar_internal_net curlimages/curl:8.10.1 -s http://ms-prestadores:8000/v1/prestadores`
- `bff-prestador` (via Kong: prefixo `/v1/prestador`): `GET /health`, `GET /tarefas/{id}`, `POST /solicitacoes/{id}/orcamentos`

## Pendências conhecidas
- `docs/02`, `03` e `04` já estão no repo e foram incorporadas à `ARCHITECTURE.md` (2026-11-17).
- Divergências docs × implementação: JWT/ACL e rate limit por rota foram implementados (itens 11–12 do log estão resolvidos, ver 17). Segue o item 10 (Elasticsearch × Postgres).
- Auth resolvida para o MVP: JWT com consumers de teste no Kong (ver `DECISIONS_LOG.md` 17). Sem emissor/`POST /auth/*` real.
- **Como integrar seu `ms-*` aos BFFs:** ver `DECISIONS_LOG.md` itens 18–20 (headers, `ENABLE_UPSTREAM_MOCK` e rotas esperadas).
- **Template:** driver trocado para `psycopg[binary]` (SQLAlchemy 2.1, DECISIONS_LOG 32). Outbox pronto para reaproveitar: `services/ms-prestadores/app/messaging.py` (DECISIONS_LOG 33).
- Pendências da Frente 3: `ms-avaliacoes` não valida status/dono da solicitação (depende do `ms-solicitacoes`, DECISIONS_LOG 37); `ServicoConcluido` e `DisponibilidadeAlterada` já são consumidos pelo projetor, mas ainda ninguém publica.
