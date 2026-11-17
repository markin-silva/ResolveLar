# DECISIONS_LOG

Entradas datadas. Registre aqui qualquer ajuste de contrato, endpoint, evento ou variável de ambiente.

## 2026-11-17 — Decisões iniciais

1. **Read DB do CQRS em PostgreSQL desnormalizado (não Elasticsearch).** Menos RAM e menos uma tecnologia para operar; suficiente para a busca por categoria/região do MVP.
2. **ChromaDB embarcado** no `ms-solicitacoes` (sem container extra), persistindo em volume/diretório local do serviço.
3. **Outbox Relay como task `asyncio` interna do `ms-pagamentos`** (sem processo/container separado), publicando em at-least-once e marcando o evento como processado após confirmação do broker.
4. **Broker = RabbitMQ.** Redis fica só para cache (triagem IA) e rate limiting do Kong.
5. **Rede:** `internal_net` com `internal: true`; só o `kong` participa de `edge_net` e `internal_net`. Porta admin do Kong (`8001`) publicada apenas em `127.0.0.1`.
6. **Eventos (novo):** exchange `resolvelar.events` (topic, durável), routing key = `tipo`. *(Envelope corrigido em 2026-11-17, ver abaixo, para seguir docs/04.)*
7. **Variáveis de ambiente (novas):** ver `.env.example` — `SERVICE_NAME`, `DATABASE_URL`, `RABBITMQ_URL`, `REDIS_URL`, senhas `POSTGRES_*`, `RABBITMQ_*`, `GEMINI_API_KEY`/`OPENAI_API_KEY`.
8. **Healthcheck do template via `python urllib`** (imagem slim não tem `curl`).

## 2026-11-17 — Alinhamento com docs/02, 03 e 04

9. **Envelope de evento = docs/04** (`eventId`, `tipo`, `versaoAgregado`, `ocorridoEm`, `dados`), em camelCase, substituindo o `event_id`/`saga_id`/`occurred_at` que eu havia definido antes de ler a doc. `sagaId` vai dentro de `dados`.
10. **Divergência consciente: Read DB em Postgres, não Elasticsearch.** docs/04 (3.1, 3.2, 3.7) prevê Elasticsearch/OpenSearch; mantemos Postgres desnormalizado (decisão 1) por RAM. Busca por raio geográfico fica simplificada (filtro por cidade/bairro/categoria). **Ação sugerida:** ajustar docs/04 ou citar a decisão no relatório.
11. **Divergência consciente: Kong sem `jwt`/`acl` por enquanto.** docs/02 prevê JWT + ACL por perfil e headers `X-User-Id`/`X-User-Role`; o `kong.yml` atual só tem `correlation-id`, `cors` e `rate-limiting` global (120/min, sem `limit_by: consumer`). Falta também um provedor de identidade (`POST /auth/*`). Em aberto: implementar auth mínima (ex.: emissor JWT simples) ou assumir identidade simulada por header no MVP.
12. **Rate limiting por rota (docs/02 2.3) ainda não aplicado:** login 5/min, `POST solicitacoes` 10/h, `POST orcamentos` 30/h. Hoje só o limite global.
13. **Eventos adicionais previstos na docs/04** (`PrestadorCadastrado`, `PerfilPrestadorAtualizado`, `AreasAtendimentoAlteradas`, `PrestadorDesativado`, `ServicoConcluido`, `DisponibilidadeAlterada`) incluídos em `ARCHITECTURE.md`. Implementar só os necessários para a demo; `ServicoConcluido` e `DisponibilidadeAlterada` são candidatos a corte.
14. **Rota pública da aprovação via Kong:** `/v1/contratante/orcamentos/{id}/aprovacao` (prefixo removido pelo Kong); o `ms-solicitacoes` expõe `/v1/orcamentos/{id}/aprovacao`. Assim `/v1/` aparece nos microsserviços, não no BFF.
15. **docs/04 exemplo "orçamento aprovado" mostra link `agendamento` (POST).** docs/03 (3.8) já pede para removê-lo, pois a SAGA reserva o horário. Implementação segue a docs/03 (`EM_CONFIRMACAO`, link `acompanhar`).
16. **Cliente do prestador:** docs/01 e 02 falam em Mobile App; o escopo do projeto define `web-prestador` (React/Vite). Mantido web.
