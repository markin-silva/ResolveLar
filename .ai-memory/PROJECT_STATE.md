# PROJECT_STATE — checklist vivo

Legenda: `[x]` pronto · `[ ]` pendente. Atualize ao concluir cada item (arquivos/rotas criados).

## Integrante 1 — Marcus (fundação, gateway, BFFs)
- [x] Fundação do repo: `.ai-memory/` (ARCHITECTURE, PROJECT_STATE, DECISIONS_LOG)
- [x] Instruções de agente: `.github/copilot-instructions.md`, `.cursorrules`
- [x] `services/_template-fastapi/` (requirements, Dockerfile multi-stage, `app/config.py`, `app/database.py`, `app/main.py` com `/health`, `X-Correlation-Id`, RFC 7807)
- [x] `docker-compose.yml` (redes `edge_net`/`internal_net`, volumes nomeados, kong, rabbitmq, redis, 6× postgres com healthcheck)
- [x] `.env.example` + `.gitignore` (ignora `.env`)
- [x] `gateway/kong.yml` completo: consumers `contratante_15`/`prest_17` (JWT HS256 + ACL), plugins `jwt`/`acl` por serviço, rate limit por rota (10/h criar solicitação, 30/h criar orçamento, 120/min demais) em Redis, `correlation-id`, `cors`
- [x] `scripts/generate_jwt.py` (tokens de teste, só stdlib)
- [x] `bff-contratante` (`services/bff-contratante`): `GET /health`, `GET /prestadores`, `POST /solicitacoes`, `GET /solicitacoes/{id}/orcamentos`, `POST /orcamentos/{id}/aprovacao`
- [x] `bff-prestador` (`services/bff-prestador`): `GET /health`, `GET /tarefas/{id}`, `GET /solicitacoes` (fila), `GET /solicitacoes/{id}` (demanda), `GET /orcamentos`, `GET /agenda`, `GET /ganhos`, `POST /solicitacoes/{id}/orcamentos`
- [x] Compose: `bff-contratante` e `bff-prestador` em `internal_net`; Kong depende deles saudáveis

## Integrante 2 — SAGA, agendamentos, pagamentos
- [x] `ms-solicitacoes` (Orquestrador SAGA persistido + HATEOAS, `POST /v1/orcamentos/{id}/aprovacao` → 202; idempotência, inbox e retomada com backoff)
- [x] `ms-agendamentos` (reserva sem sobreposição + confirmação + `LiberarReserva` idempotente)
- [x] `ms-pagamentos` (Transactional Outbox + Relay Worker `asyncio` com publisher confirms + gatilhos de falha + conciliação/estorno simulado)
- [x] Dockerfiles + entradas Compose
- [x] Testes locais em `services/tests-frente2/`: **17 passaram** (Python 3.14, SQLite, HTTP/AMQP simulados; inclui contratos dos YAMLs). Compilação Python verificada. Roteiro `scripts/demo-frente2.py`; guia `docs/05-frente2-execucao.md`
- [ ] Validar Frente 2 com PostgreSQL/RabbitMQ reais e aplicar seus manifests em cluster (Docker indisponível no ambiente da implementação; testes locais usam SQLite e transportes simulados)

## Integrante 3 — Prestadores, avaliações, IA
- [x] `ms-prestadores` (`services/ms-prestadores`): CQRS com `db-prestadores-write` (agregado + outbox) e `db-prestadores-read` (`prestador_view` desnormalizada); relay da outbox e projetor RabbitMQ idempotente (eventId + versaoAgregado, retry + DLQ); cache Redis com invalidação pelo projetor; seed de 11 prestadores
- [x] `ms-avaliacoes` (`services/ms-avaliacoes`): `POST /v1/solicitacoes/{id}/avaliacao` + Outbox publicando `AvaliacaoRegistrada` (notaMedia/totalAvaliacoes) → Read DB do `ms-prestadores`; seed de 10 avaliações
- [x] Triagem IA (`services/ms-triagem`, serviço próprio — ver DECISIONS_LOG 37): cadeia LCEL RAG (ChromaDB) → LLM estruturado (Gemini/OpenAI) → `@tool buscar_prestadores` (ms-prestadores real); timeout, retry com backoff, circuit breaker, cache Redis e fallback por regras
- [x] Script de avaliação: `docker compose exec ms-triagem python -m app.avaliacao` (5 perguntas × com/sem RAG, acerto, cobertura, latência, tokens, custo)
- [x] Avaliação com LLM real (Gemini `gemini-3.5-flash-lite`) em `docs/05-avaliacao-triagem.md`: 5/5 categorias e urgências; cobertura de segurança 75% com RAG × 40% sem; ~US$ 0,0007/triagem; latência alta do provedor no dia (p50 ~10s) documentada
- [x] Dockerfiles + Compose desses serviços
- Testado em Docker Desktop (Windows, 2026-11-19): busca/triagem/avaliação via Kong com JWT, 409/422/403, cache HIT/MISS, Redis fora, ms-prestadores fora, chave de LLM inválida e Gemini lento (fallback + circuit breaker), cache HIT de resposta do LLM (19s → 0,6ms), primeiro boot com fila ainda não declarada

## Integrante 4 — Frontends
- [x] `web-contratante` (`:3001`): triagem IA (`POST /triagem`), busca CQRS, criação de solicitação, comparação de orçamentos com botões **Aprovar/Recusar guiados por `_links`**, cartão `pm_tok_ok`/`pm_tok_recusado`, `Idempotency-Key` nova por tentativa (`crypto.randomUUID`), **polling da SAGA** (2 s, até ~20 s) mostrando `CONFIRMADA` ou a compensação (`AGUARDANDO_ACEITE` + motivo), **avaliação** 1–5 + comentário (`POST /solicitacoes/{id}/avaliacao`) e releitura da busca (nota atualizada via CQRS)
- [x] `web-prestador` (`:3002`): tela de entrada por token; consulta de tarefa **por ID** (o BFF não tem listagem), envio de orçamento em centavos, detalhes técnicos e decomposição financeira vinda do BFF; identificação lida do `sub` do JWT. **Sem modo demonstração:** todo erro da API aparece como erro (DECISIONS_LOG 63)
- [x] Dockerfiles multi-stage (Node/Vite → `nginx:1.27-alpine`), SPA fallback, `HEALTHCHECK`, `.dockerignore`, `npm ci --no-audit --no-fund` (com `package-lock.json`); Compose em `edge_net` nas portas `3001`/`3002`
- [x] Verificação: builds Vite dos 2 apps, imagens Nginx sobem (`healthy`, SPA fallback 200), 5 testes de fluxo do contratante (fetch simulado) e 4 do BFF passam. **Não foi executado o fluxo ponta a ponta com a stack real (Kong + ms-*).**

## Por etapa
### Parte 3 — Docker
- [x] Compose de infraestrutura base + BFFs
- [x] Compose dos 6 `ms-*` e dos 2 `web-*`. **Kubernetes removido do projeto** por orientação do professor (DECISIONS_LOG 62): só Docker/Compose
### Parte 4 — Microsserviços, SAGA, CQRS, RAG, Frontends
- [x] Microsserviços (6/6 no Compose) · [ ] SAGA (código pronto; falta a correção do driver, ver Pendências) · [x] CQRS · [x] RAG/LangChain · [x] Frontends

## Endpoints reais implementados
- Frente 2: solicitações/orçamentos/aceite/recusa/consulta com HATEOAS; reserva/confirmação/liberação e consulta de agendamentos; pagamento/conciliação/estorno/repasses; `/health` e `/ready` nos três. Contratos completos em `docs/05-frente2-execucao.md` e decisões 29–36.
- Template: `GET /health` (cada serviço derivado herda).
- `bff-contratante` (via Kong: prefixo `/v1/contratante`): `GET /health`, `GET /prestadores`, `POST /triagem`, `POST /solicitacoes`, `GET /solicitacoes/{id}` (**novo:** estado + SAGA, usado no polling), `GET /solicitacoes/{id}/orcamentos` (agora com `status_codigo`, `motivo` e `_links` por orçamento), `POST /solicitacoes/{id}/avaliacao`, `POST /orcamentos/{id}/aprovacao`, `POST /orcamentos/{id}/recusa` (**novo**), `GET /solicitacoes` (meus pedidos)
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
- **Template:** driver trocado para `psycopg[binary]` (SQLAlchemy 2.1, DECISIONS_LOG 40). Outbox pronto para reaproveitar: `services/ms-prestadores/app/messaging.py` (DECISIONS_LOG 41).
- Pendências da Frente 3: `ms-avaliacoes` não valida status/dono da solicitação (depende do `ms-solicitacoes`, DECISIONS_LOG 45); `ServicoConcluido` e `DisponibilidadeAlterada` já são consumidos pelo projetor, mas ainda ninguém publica.
- **Frente 2 não sobe no Docker (2026-11-24):** `ms-solicitacoes`, `ms-agendamentos` e `ms-pagamentos` reiniciam com `ModuleNotFoundError: No module named 'psycopg'`. Correção testada localmente (a demo da SAGA passou, inclusive via Kong): nos 3 `requirements.txt` trocar `psycopg2-binary==2.9.13` por `psycopg[binary]==3.3.9`, e nos 3 `app/core.py` trocar `"postgresql+psycopg2"` por `"postgresql+psycopg"` (DECISIONS_LOG 40).
- **Frontends:** `clients/web-contratante` em `http://localhost:3001` e `clients/web-prestador` em `http://localhost:3002` (alinhado ao CORS do Kong). Só falam com `/v1/...` no próprio origin; o Nginx do contêiner encaminha ao Kong (`KONG_UPSTREAM`, padrão `kong:8000`). Sem token mostram só a tela de entrada; com token chamam os BFFs e os erros aparecem como erros.
- **Fluxo de usabilidade (docs/06):** Fase 0 (Kong com usuários fixos) e Fase 1 (listagens, visão pública da demanda, agenda, ganhos e regra de avaliação) **concluídas e validadas na stack**. Faltam: Fase 2 (consumer por perfil + login + segredo do JWT fora do `kong.yml`), Fase 3 (frontends novos) e Fase 4 (documentação e passo a passo para os integrantes).
- **Pendências dos frontends:** (a) validar o fluxo no navegador com a stack completa; (b) os frontends ainda usam o fluxo antigo (token colado, ID digitado) até a Fase 3; (c) o `web-prestador` ainda não consome a fila (`GET /solicitacoes` do BFF Prestador).
