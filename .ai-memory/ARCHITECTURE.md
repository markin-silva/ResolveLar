# ARCHITECTURE — ResolveLar (GCC129 · Sistemas Distribuídos)

> Fonte de verdade para stack, portas, hosts, contratos REST e eventos. Não invente nomes que contrariem este arquivo.
> Qualquer novo endpoint, evento ou variável de ambiente deve ser registrado em `DECISIONS_LOG.md`.

## 1. Stack padronizada

| Camada | Tecnologia |
|---|---|
| BFFs e microsserviços | Python 3.12 + FastAPI + SQLModel + Pydantic |
| Bancos | PostgreSQL 16 (`postgres:16-alpine`) — um por serviço |
| Broker | RabbitMQ (`rabbitmq:3-management-alpine`) |
| Cache / rate limit | Redis (`redis:7-alpine`) |
| API Gateway | Kong 3.6 (`kong:3.6`), modo DB-less |
| Clientes web | React + Vite, servidos por Nginx (`nginx:alpine`) |
| Triagem IA | LangChain + ChromaDB embarcado, no serviço próprio `ms-triagem` (ver DECISIONS_LOG 37) |

Decisão de broker: **RabbitMQ** (o diagrama do doc 01 cita "Redis/RabbitMQ"; vale RabbitMQ para eventos, Redis só para cache e rate limit).

## 2. Topologia de rede e portas internas

Redes Docker:
- `edge_net`: exposta. Participam `kong`, `web-contratante`, `web-prestador`.
- `egress_net`: saída para a internet só para o `ms-triagem` (chamar a API do LLM). Os demais ms continuam isolados na `internal_net`.
- `internal_net` (`internal: true`): BFFs, microsserviços, bancos, RabbitMQ e Redis. Só o `kong` participa das duas redes.

| Container | Porta interna | Observações |
|---|---|---|
| `kong` | `8000` (proxy, externa), `8001` (admin) | `/v1/contratante/*` → `bff-contratante:8000`; `/v1/prestador/*` → `bff-prestador:8000` (`strip_path: true`); `POST /v1/contratante/orcamentos/{id}/aprovacao` → `orquestrador-saga:8000` (regex + reescrita da URI) |
| `bff-contratante` | `8000` | |
| `bff-prestador` | `8000` | |
| `ms-prestadores` | `8000` | `db-prestadores-write` + `db-prestadores-read` (Postgres desnormalizado, CQRS) |
| `orquestrador-saga` | `8000` | Coordena a SAGA de contratação; **fora dos ms de domínio** (sem dados de negócio); chamado direto pelo Kong; consome eventos de pagamento → `db-orquestrador` (só estado da SAGA + inbox) |
| `ms-solicitacoes` | `8000` | Domínio de pedidos e orçamentos; participante da SAGA (comandos `contratacao`) → `db-solicitacoes` |
| `ms-agendamentos` | `8000` | → `db-agendamentos` |
| `ms-pagamentos` | `8000` | Transactional Outbox + worker `asyncio` publicando no RabbitMQ → `db-pagamentos` |
| `ms-avaliacoes` | `8000` | Publica `AvaliacaoRegistrada` → `db-avaliacoes` |
| `ms-auth` | `8000` | Login dos usuários fixos e emissão do JWT; sem banco; só `internal_net`; via Kong em `/v1/auth/*` (pública, 5/min por IP no login) |
| `ms-triagem` | `8000` | Triagem IA (LangChain + ChromaDB embarcado em `/data/chroma`, volume `chroma_data`) + Redis; sem banco; `internal_net` + `egress_net` |
| `web-contratante` | host `3001` → Nginx `80` | |
| `web-prestador` | host `3002` → Nginx `80` | |
| `rabbitmq` | `5672` (AMQP), `15672` (management) | |
| `redis` | `6379` | |
| `db-*` | `5432` | `db-prestadores-write`, `db-prestadores-read`, `db-solicitacoes`, `db-agendamentos`, `db-pagamentos`, `db-avaliacoes`, `db-orquestrador` |

Volumes nomeados: `pg_prestadores_write`, `pg_prestadores_read`, `pg_solicitacoes`, `pg_agendamentos`, `pg_pagamentos`, `pg_avaliacoes`, `pg_orquestrador`, `rabbitmq_data`, `chroma_data`.

## 3. Contratos e regras críticas

- Erros: RFC 7807, `Content-Type: application/problem+json` (`type`, `title`, `status`, `detail`, `instance`).
- Valores monetários: **centavos, `int`**.
- Versionamento: prefixo `/v1/`.
- HATEOAS: `_links` em orçamentos e solicitações.
- Rastreabilidade: header `X-Correlation-Id` gerado pelo Kong (plugin `correlation-id`) e repassado por todos os serviços.
- Resiliência: toda chamada HTTP entre serviços com timeout curto (3s). Consumidores RabbitMQ idempotentes (checar `event_id`/`saga_id`).

### SAGA orquestrada (orquestrador: `orquestrador-saga`, fora dos microsserviços)
Kong → `orquestrador-saga` `POST /v1/orcamentos/{id}/aprovacao` → **`202 Accepted`**, solicitação `EM_CONFIRMACAO`.
O orquestrador não tem domínio; o `ms-solicitacoes` é participante como os outros (DECISIONS_LOG 82).

1. Iniciar a contratação no `ms-solicitacoes` (síncrono: valida dono/orçamento e trava a solicitação).
2. Reserva de horário no `ms-agendamentos`.
3. Cobrança no `ms-pagamentos` (**transação pivô**).
4. Outbox do `ms-pagamentos` publica `PagamentoAprovado` ou `PagamentoRecusado` no RabbitMQ → orquestrador.
5. Aprovado: confirmar reserva e confirmar contratação no `ms-solicitacoes`. Recusado: `LiberarReserva` e cancelar a contratação.

**Gatilho determinístico de falha (demo):** no `ms-pagamentos`, `meioPagamentoId == "pm_tok_recusado"` **ou** valor `> 500000` centavos força recusa e dispara a compensação.

#### Detalhes da SAGA (docs/03)
- Entrada pública: `POST /v1/contratante/orcamentos/{id}/aprovacao` no Kong → `orquestrador-saga` `POST /v1/orcamentos/{id}/aprovacao` (não passa pelo BFF; Kong põe `X-User-Id` do `sub` e `X-User-Role: contratante`). Header `Idempotency-Key`. Body: `{"horarioEscolhido": ISO-8601, "meioPagamentoId": "pm_tok_..."}` (token, nunca dados de cartão).
- Resposta `202`: `{"sagaId","solicitacaoId","orcamentoId","status":"EM_CONFIRMACAO","_links":{"acompanhar":{"href":"/v1/contratante/solicitacoes/{id}","method":"GET"}}}`. Dono errado → `403`; orçamento vencido/recusado/já consumido → `409`; horário passado → `422`; `ms-solicitacoes` fora → `503` (SAGA `ABORTADA`).
- Estados — Solicitação: `EM_CONFIRMACAO`, `CONFIRMADA`, `AGUARDANDO_ACEITE`. SAGA: `EM_ANDAMENTO`, `CONCLUIDA`, `COMPENSADA`, `COMPENSACAO_PENDENTE`, `REJEITADA`, `ABORTADA`. Reserva: `RESERVADA`, `CONFIRMADA`, `LIBERADA`. Pagamento: `APROVADO`, `RECUSADO`, `CANCELADO`, `ESTORNADO`.
- Etapas (`orquestrador-saga/app/worker.py`): `INICIAR` → `RESERVAR` → `PAGAR` → `AGUARDAR_EVENTO` → `CONFIRMAR_RESERVA` → `CONFIRMAR_SOLICITACAO`; compensações `ESTORNAR` → `LIBERAR` → `CANCELAR_SOLICITACAO`, ou `ABORTAR`.
- Comandos do orquestrador são HTTP síncronos (timeout 3s): `ms-solicitacoes` (`POST /v1/orcamentos/{id}/contratacao`, `.../confirmacao`, `.../cancelamento`), `ms-agendamentos` (reservar, confirmar, `LiberarReserva(reservaId)`) e `ms-pagamentos` (cobrar, estornar); o resultado do pagamento volta por evento (Outbox). Estado da SAGA persistido em `db-orquestrador`; tudo idempotente por `sagaId`. O BFF lê o andamento em `GET /v1/sagas/{id}`.
- Timeout no `ms-pagamentos` **não** é recusa: consultar/conciliar pela chave idempotente antes de liberar a reserva.

### Eventos RabbitMQ
Exchange `resolvelar.events` (tipo `topic`, durável). Routing key = `tipo` do evento. Envelope (docs/04):

```json
{"eventId": "evt_...", "tipo": "PagamentoAprovado", "versaoAgregado": 1,
 "ocorridoEm": "2026-10-21T14:58:00Z", "dados": {"sagaId": "saga_52", "...": "..."}}
```
Consumidor idempotente: ignora `eventId` já processado; projeções ignoram `versaoAgregado` <= versão já aplicada.

| Evento | Produtor | Consumidor(es) |
|---|---|---|
| `PagamentoAprovado` | `ms-pagamentos` (Outbox) | `orquestrador-saga` (fila `resolvelar.orquestrador.pagamentos`) |
| `PagamentoRecusado` | `ms-pagamentos` (Outbox) | `orquestrador-saga` |
| `AvaliacaoRegistrada` | `ms-avaliacoes` | `ms-prestadores` (`notaMedia`, `totalAvaliacoes` no Read DB) |
| `PrestadorCadastrado`, `PerfilPrestadorAtualizado`, `AreasAtendimentoAlteradas`, `PrestadorDesativado` | `ms-prestadores` (Outbox) | projetor do Read DB (`ms-prestadores`) |
| `ServicoConcluido` | `ms-solicitacoes` | `ms-prestadores` (`servicosConcluidos`) |
| `DisponibilidadeAlterada` | `ms-agendamentos` | `ms-prestadores` (`disponivelHoje`) |

### Gateway/BFF (docs/02)
- Kong remove o prefixo (`strip_path: true`); o BFF recebe caminhos limpos (ex.: `/solicitacoes/sol_8f21`). BFFs não têm banco e agregam com `httpx` + `asyncio.gather`, timeout curto.
- Kong injeta `X-Correlation-Id`; com JWT ativo também `X-User-Id` e `X-User-Role` (BFF confia neles; autorização fina por recurso é do BFF). Ver `DECISIONS_LOG.md` sobre JWT no MVP.
- BFF Contratante: payload resumido, `valor` + `valor_formatado`, sem taxa. BFF Prestador: bruto/taxa/líquido em centavos (calculados pelo `ms-pagamentos`), contato e endereço só após agendamento confirmado.
- Chamadas do BFF aos ms usam as rotas `/v1/...` dos microsserviços (ex.: `/v1/solicitacoes/{id}`, `/v1/agendamentos?solicitacao_id=`, `/v1/repasses?solicitacao_id=`).

### CQRS (`ms-prestadores`)
Escrita em `db-prestadores-write` (comando grava evento na tabela `outbox` na mesma transação); leitura/busca em `db-prestadores-read` (tabela desnormalizada, Postgres, **sem Elasticsearch** — diverge de docs/04, ver `DECISIONS_LOG.md`). Projetor consome eventos, é idempotente por `eventId`/`versaoAgregado` e invalida cache Redis (`prestador:{id}`). Falhas: retry com backoff + DLQ.
Endpoints de comando: `POST /v1/prestadores`, `PATCH /v1/prestadores/{id}`, `PUT /v1/prestadores/{id}/areas-atendimento`, `DELETE /v1/prestadores/{id}`. Query: `GET /v1/prestadores?cidade=&categoria=&page=&size=`, `GET /v1/prestadores/{id}`.
**Implementado (Frente 3):** relay da outbox e projetor rodam como tasks asyncio dentro do `ms-prestadores`. Fila `ms-prestadores.projecao` (durável) ligada a `PrestadorCadastrado`, `PerfilPrestadorAtualizado`, `AreasAtendimentoAlteradas`, `PrestadorDesativado`, `AvaliacaoRegistrada`, `ServicoConcluido`, `DisponibilidadeAlterada`; DLQ `ms-prestadores.projecao.dlq` via exchange `resolvelar.dlx` (direct) após 3 tentativas. Cache: `prestador:{id}` (60s) e `busca:*` (30s), header `X-Cache: HIT|MISS`; o projetor invalida os dois. Categorias válidas: `GET /v1/categorias` (`eletricista`, `encanador`, `tecnico-gas`, `pedreiro`, `pintor`, `marceneiro`, `chaveiro`, `instalador`).

### Avaliações (`ms-avaliacoes`)
`POST /v1/solicitacoes/{id}/avaliacao` (body `{prestadorId, nota 1..5, comentario?}`, `X-User-Id` obrigatório; 201 + `Location`; 409 se a solicitação já foi avaliada; 403 se `X-User-Role` ≠ `contratante`), `GET /v1/avaliacoes/{id}`, `GET /v1/avaliacoes?prestador_id=&page=&size=` (com `resumo`). Na mesma transação: avaliação + `reputacao_prestador` (travada com `FOR UPDATE`) + outbox `AvaliacaoRegistrada` com `dados: {avaliacaoId, solicitacaoId, prestadorId, contratanteId, nota, notaMedia, totalAvaliacoes}` e `versaoAgregado = totalAvaliacoes` daquele prestador.
HATEOAS: orçamento `PENDENTE` expõe `aprovar`/`recusar`; `APROVADO` e `EXPIRADO` trocam os links (docs/04). Como a aprovação é a SAGA, após `aprovar` o estado é `EM_CONFIRMACAO` (sem o link `agendamento` do exemplo da doc 04).

### Triagem IA (Parte 4, `ms-triagem`)
- Cadeia LCEL: RAG (ChromaDB) → `prompt | LLM.with_structured_output` → `@tool buscar_prestadores` (HTTP `GET /v1/prestadores` no `ms-prestadores`). A tool é chamada pela cadeia com a categoria classificada: o LLM nunca inventa prestadores.
- RAG: `services/ms-triagem/app/conhecimento/*.md`, um chunk por seção `##`; embeddings locais (all-MiniLM-L6-v2 ONNX, baixado no build com retry), reindexa quando os .md mudam. `EmbeddingLocal` reaproveita UMA sessão ONNX com 2 threads (`EMBEDDING_THREADS`) e é aquecido na subida (DECISIONS_LOG 83).
- LLM: Gemini (`gemini-3.5-flash-lite`) ou OpenAI (`gpt-4o-mini`) por `LLM_PROVIDER`/chave; sem chave → fallback.
- Prazo da triagem inteira: `TRIAGEM_DEADLINE_SECONDS=7` (RAG + LLM + tool); o LLM usa o menor entre o seu orçamento e o que sobra do prazo (DECISIONS_LOG 84).
- Resiliência: timeout por tentativa (4,5s, via `asyncio.wait_for`; não vai na requisição ao Gemini) + retry com backoff só em erro transitório + orçamento total (5s; RAG 0,7–1,4s + tool ~0,2s + cancelamento até ~0,9s ficam fora dele, então a resposta volta em ~7,5s no pior caso, abaixo dos 9s do BFF) + circuit breaker (3 falhas → 30s aberto) + fallback determinístico (regras + trechos do RAG) + cache Redis `triagem:v1:*` (1h, só respostas do LLM). Tool: timeout 2s + 1 retry; falhou → `prestadoresSugeridos: []` + aviso. Redis fora → segue sem cache.
- API: `POST /v1/triagem?rag=true&cache=true` body `{descricao, cidade?, uf?}` → `{triagemId, categoria, urgencia (EMERGENCIA|ALTA|MEDIA|BAIXA), resumo, orientacoesSeguranca[], perguntasComplementares[], prestadoresSugeridos[], fontes[], modo (llm|fallback), rag, cache, avisos[], metricas{latenciaMs, modelo, tokensEntrada, tokensSaida, custoEstimadoUsd}, _links{buscarPrestadores, criarSolicitacao}}`. Depuração: `GET /v1/triagem/base-conhecimento?q=`. Via Kong: `POST /v1/contratante/triagem`.
- Avaliação: `docker compose exec ms-triagem python -m app.avaliacao` (5 perguntas × com/sem RAG; acerto, cobertura de segurança, latência, tokens, custo). Resultado em `docs/05-avaliacao-triagem.md`.

## 4. Variáveis de ambiente
Ver `.env.example` (raiz). Nada de credenciais hardcoded: código lê via `os.getenv`/`pydantic-settings`; Compose via `.env`.
Variáveis padrão de cada serviço Python: `SERVICE_NAME`, `DATABASE_URL`, `RABBITMQ_URL`, `REDIS_URL`.

## 5. Estrutura do repositório
```
.ai-memory/            memória compartilhada (este diretório)
docs/                  documentação de arquitetura
gateway/kong.tpl.yml   Kong declarativo (template; o kong.yml é gerado na subida com JWT_SECRET)
services/_template-fastapi/   template base dos serviços Python
docker-compose.yml     infraestrutura base + serviços
```
