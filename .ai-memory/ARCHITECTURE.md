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
| Triagem IA | LangChain + ChromaDB embarcado (dentro do `ms-solicitacoes`) |

Decisão de broker: **RabbitMQ** (o diagrama do doc 01 cita "Redis/RabbitMQ"; vale RabbitMQ para eventos, Redis só para cache e rate limit).

## 2. Topologia de rede e portas internas

Redes Docker:
- `edge_net`: exposta. Participam `kong`, `web-contratante`, `web-prestador`.
- `internal_net` (`internal: true`): BFFs, microsserviços, bancos, RabbitMQ e Redis. Só o `kong` participa das duas redes.

| Container | Porta interna | Observações |
|---|---|---|
| `kong` | `8000` (proxy, externa), `8001` (admin) | `/v1/contratante/*` → `bff-contratante:8000`; `/v1/prestador/*` → `bff-prestador:8000` (`strip_path: true`) |
| `bff-contratante` | `8000` | |
| `bff-prestador` | `8000` | |
| `ms-prestadores` | `8000` | `db-prestadores-write` + `db-prestadores-read` (Postgres desnormalizado, CQRS) |
| `ms-solicitacoes` | `8000` | Orquestrador da SAGA + Triagem IA (LangChain + ChromaDB) → `db-solicitacoes` |
| `ms-agendamentos` | `8000` | → `db-agendamentos` |
| `ms-pagamentos` | `8000` | Transactional Outbox + worker `asyncio` publicando no RabbitMQ → `db-pagamentos` |
| `ms-avaliacoes` | `8000` | Publica `AvaliacaoRegistrada` → `db-avaliacoes` |
| `web-contratante` | host `3001` → Nginx `80` | |
| `web-prestador` | host `3002` → Nginx `80` | |
| `rabbitmq` | `5672` (AMQP), `15672` (management) | |
| `redis` | `6379` | |
| `db-*` | `5432` | `db-prestadores-write`, `db-prestadores-read`, `db-solicitacoes`, `db-agendamentos`, `db-pagamentos`, `db-avaliacoes` |

Volumes nomeados: `pg_prestadores_write`, `pg_prestadores_read`, `pg_solicitacoes`, `pg_agendamentos`, `pg_pagamentos`, `pg_avaliacoes`, `rabbitmq_data`.

## 3. Contratos e regras críticas

- Erros: RFC 7807, `Content-Type: application/problem+json` (`type`, `title`, `status`, `detail`, `instance`).
- Valores monetários: **centavos, `int`**.
- Versionamento: prefixo `/v1/`.
- HATEOAS: `_links` em orçamentos e solicitações.
- Rastreabilidade: header `X-Correlation-Id` gerado pelo Kong (plugin `correlation-id`) e repassado por todos os serviços.
- Resiliência: toda chamada HTTP entre serviços com timeout curto (3s). Consumidores RabbitMQ idempotentes (checar `event_id`/`saga_id`).

### SAGA orquestrada (orquestrador: `ms-solicitacoes`)
`POST /v1/orcamentos/{id}/aprovacao` → **`202 Accepted`**, estado `EM_CONFIRMACAO`.

1. Reserva de horário no `ms-agendamentos`.
2. Cobrança no `ms-pagamentos` (**transação pivô**).
3. Outbox do `ms-pagamentos` publica `PagamentoAprovado` ou `PagamentoRecusado` no RabbitMQ.
4. Orquestrador confirma a reserva (aprovado) ou executa a compensação `LiberarReserva` (recusado).

**Gatilho determinístico de falha (demo):** no `ms-pagamentos`, `meioPagamentoId == "pm_tok_recusado"` **ou** valor `> 500000` centavos força recusa e dispara a compensação.

#### Detalhes da SAGA (docs/03)
- Entrada: `POST /v1/orcamentos/{id}/aprovacao` (rota do `ms-solicitacoes`; via Kong: `/v1/contratante/orcamentos/{id}/aprovacao` → BFF → ms). Header `Idempotency-Key`. Body: `{"horarioEscolhido": ISO-8601, "meioPagamentoId": "pm_tok_..."}` (token, nunca dados de cartão).
- Resposta `202`: `{"sagaId","solicitacaoId","orcamentoId","status":"EM_CONFIRMACAO","_links":{"acompanhar":{"href":"/v1/solicitacoes/{id}","method":"GET"}}}`. Orçamento vencido/recusado/já consumido → `409`.
- Estados — Solicitação: `EM_CONFIRMACAO`, `CONFIRMADA`, `AGUARDANDO_ACEITE`. SAGA: `EM_ANDAMENTO`, `CONCLUIDA`, `COMPENSADA`, `COMPENSACAO_PENDENTE`. Reserva: `RESERVADA`, `CONFIRMADA`, `LIBERADA`. Pagamento: `APROVADO`, `RECUSADO`, `CANCELADO`, `ESTORNADO`.
- Comandos do orquestrador são HTTP síncronos (timeout 3s) para `ms-agendamentos` (reservar, confirmar, `LiberarReserva(reservaId)`) e `ms-pagamentos` (processar pagamento); o resultado do pagamento volta por evento (Outbox). Estado da SAGA persistido em `db-solicitacoes`; tudo idempotente por `sagaId`.
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
| `PagamentoAprovado` | `ms-pagamentos` (Outbox) | `ms-solicitacoes` |
| `PagamentoRecusado` | `ms-pagamentos` (Outbox) | `ms-solicitacoes` |
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
HATEOAS: orçamento `PENDENTE` expõe `aprovar`/`recusar`; `APROVADO` e `EXPIRADO` trocam os links (docs/04). Como a aprovação é a SAGA, após `aprovar` o estado é `EM_CONFIRMACAO` (sem o link `agendamento` do exemplo da doc 04).

### Triagem IA (Parte 4, `ms-solicitacoes`)
- LangChain (cadeia LCEL) + `@tool` que consulta prestadores reais via HTTP no `ms-prestadores`.
- RAG completo com ChromaDB embarcado; base de conhecimento em Markdown (segurança e categorias).
- Resiliência obrigatória: timeout + retry com backoff, cache no Redis, fallback determinístico.
- Relatório de avaliação: 5 perguntas com/sem RAG, latência e custo.

## 4. Variáveis de ambiente
Ver `.env.example` (raiz). Nada de credenciais hardcoded: código lê via `os.getenv`/`pydantic-settings`; Compose via `.env`; Kubernetes via `ConfigMap`/`Secret` (`k8s/`).
Variáveis padrão de cada serviço Python: `SERVICE_NAME`, `DATABASE_URL`, `RABBITMQ_URL`, `REDIS_URL`.

## 5. Estrutura do repositório
```
.ai-memory/            memória compartilhada (este diretório)
docs/                  documentação de arquitetura
gateway/kong.yml       Kong declarativo
services/_template-fastapi/   template base dos serviços Python
k8s/                   manifests da Parte 3
docker-compose.yml     infraestrutura base
```
