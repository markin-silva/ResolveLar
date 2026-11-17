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

## 2026-11-17 — Gateway completo, BFFs e Kubernetes (Integrante 1)

17. **Auth do MVP = JWT HS256 com consumers de teste no Kong (resolve itens 11 e 12).** `contratante_15` (grupo ACL `contratante`, key `contratante-key`) e `prest_17` (grupo `prestador`, key `prestador-key`), segredo `resolvelar-jwt-secret-2026` — **público, só para demo local**. O Kong casa o token pela claim `iss` (= `key`) e exige `exp`. Gere tokens com `python3 scripts/generate_jwt.py`. Não há `POST /auth/*`; um provedor real fica fora do escopo. Rate limit (`policy: redis`, `limit_by: consumer`): 120/min geral; `POST /v1/contratante/solicitacoes` 10/h; `POST /v1/prestador/solicitacoes/{id}/orcamentos` 30/h. As rotas limitadas usam regex + `request-transformer` (`strip_path` não funciona com regex), então qualquer rota nova com prefixo próprio precisa de rota própria no `kong.yml`.
18. **Headers de identidade injetados pelo Kong** após validar o JWT: `X-Consumer-Username` (id do usuário, ex. `contratante_15`) e `X-Consumer-Groups` (role: `contratante`|`prestador`); também `X-Consumer-Id` e `X-Credential-Identifier`. Os BFFs leem `X-Consumer-Username` com **fallback `X-User-Id`** (testar o BFF sem Kong); sem nenhum dos dois, `401` (RFC 7807). O BFF NÃO revalida o JWT. Para os microsserviços, o BFF repassa `X-User-Id`, `X-User-Role`, `X-Correlation-Id` e `Idempotency-Key` (na aprovação). Autorização fina (dono do recurso → `403`) é do BFF.
19. **`ENABLE_UPSTREAM_MOCK` (nova variável, padrão `true` no `.env.example` e no ConfigMap).** Com `true`, se uma chamada do BFF a um `ms-*` falhar por **erro de rede** (`httpx.RequestError`, serviço fora do ar), o BFF devolve payloads de exemplo da docs/02 e marca a resposta com `X-Mock-Upstream: true`. Um `ms-*` que **responde** (mesmo 4xx/5xx) nunca é mockado: o erro é repassado. Com `false`: falha em dado essencial → `503`; falha em dado opcional (agendamento/pagamentos no BFF Prestador, reputação no BFF Contratante) → bloco omitido (degradação graciosa). **Para integrar seu ms:** suba-o com o nome de host de `ARCHITECTURE.md` na `internal_net` e responda as rotas abaixo; o mock desliga sozinho para esse serviço (os demais continuam mockados). Quando todos estiverem prontos, ponha `ENABLE_UPSTREAM_MOCK=false`.
20. **Rotas que os BFFs chamam nos microsserviços (contrato esperado, camelCase da docs/04; as docs 02/04 divergem em nomes, o BFF aceita camelCase e snake_case):**
    - `ms-prestadores`: `GET /v1/prestadores?cidade=&categoria=&page=&size=` (resposta lista ou `{items:[...]}`), `GET /v1/prestadores/{id}` (`prestadorId, nome, fotoUrl, notaMedia, servicosConcluidos, ...`).
    - `ms-solicitacoes`: `GET /v1/solicitacoes/{id}` (`status`, `titulo|descricao`, `contratanteId`, `prestadorId`, `detalhesTecnicos`, `local`, `cliente`), `GET /v1/solicitacoes/{id}/orcamentos` (**nova rota**: `{items:[{id, status, valor:{centavos,moeda}, prazo|prazoEstimadoDias, prestador:{id,nome,notaMedia}}]}`), `POST /v1/solicitacoes`, `POST /v1/solicitacoes/{id}/orcamentos`, `POST /v1/orcamentos/{id}/aprovacao` (202).
    - `ms-agendamentos`: `GET /v1/agendamentos?solicitacao_id=` (`{items:[{inicio, fim}]}`).
    - `ms-pagamentos`: `GET /v1/repasses?solicitacao_id=` (`{items:[{moeda, valor_bruto_centavos, taxa_plataforma_percentual, taxa_plataforma_centavos, valor_liquido_centavos, previsao_repasse}]}`). A taxa e o líquido são calculados aqui, nunca no BFF.
21. **Headers de resposta dos BFFs:** `X-Pod-Name` (= `socket.gethostname()`, nome do Pod no Kubernetes; prova do balanceamento), `X-Correlation-Id`, `X-Mock-Upstream` (quando mockado). `GET /health` devolve também `pod` e `mockUpstream`.
22. **`services/*/app/core.py` é idêntico nos dois BFFs** (identidade, erros RFC 7807, mock, `X-Pod-Name`). Duplicado de propósito (cada serviço tem seu `Dockerfile`/contexto de build). Alterou? Copie para o outro BFF.
23. **Kubernetes:** o Ingress (`05-ingress.yaml`) aponta para o **Service `kong`**, não direto para os BFFs, para manter JWT/ACL/rate limit/correlation-id iguais ao Compose. O `kong.yml` vai para o cluster via ConfigMap gerado por `scripts/sync-kong-configmap.sh` (`k8s/01-kong-config.yaml`). Admin do Kong no cluster só em `127.0.0.1` do Pod. Substituiu o antigo `04-ingress.yaml` (que usava `rewrite-target` e não passava pelo Kong).
24. **Variáveis de ambiente novas:** `ENABLE_UPSTREAM_MOCK`, `JWT_SECRET` (referência para `generate_jwt.py` e Secret; o Kong lê o segredo do `kong.yml`), `HTTP_TIMEOUT_SECONDS` agora é lido como `float` pelos BFFs.
25. **Correção no template:** o handler de 422 passou a serializar só `loc/msg/type` (o `exc.errors()` do Pydantic v2 pode conter objetos não serializáveis em `ctx`).

## 2026-11-17 — Ajustes após o primeiro deploy em kind (Integrante 1)

26. **Limites de memória:** Kong sobe com `limits.memory: 1Gi` (era 512Mi, causava `OOMKilled`); RabbitMQ `1Gi` com probe de 10s de timeout (o ping demorava mais que 1s no primeiro boot).
27. **Balanceamento entre réplicas dos BFFs:** o Kong mantinha uma conexão keep-alive com o upstream, e todas as requisições caíam no mesmo Pod. Correção: `KONG_UPSTREAM_KEEPALIVE_POOL_SIZE=0` e `KONG_UPSTREAM_KEEPALIVE_MAX_REQUESTS=1` no Deployment do Kong (só Kubernetes; o Compose não precisou). Trade-off: uma conexão nova por requisição.
28. **Testado em kind v1.31 (Linux x86_64).** Minikube e Docker Desktop não foram testados.
