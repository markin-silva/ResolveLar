# Frente 2 — SAGA, agendamentos e pagamentos

Implementação em `services/orquestrador-saga` (coordena a SAGA, fora dos microsserviços),
`services/ms-solicitacoes`, `services/ms-agendamentos` e
`services/ms-pagamentos`. Depois da devolutiva da Parte 2, a orquestração saiu do
`ms-solicitacoes` para o `orquestrador-saga`, que o Kong chama direto (ver `docs/03`).
O pagamento é um **simulador**, sem chamada a operadora real.

## Subir e demonstrar

Com Docker e Compose instalados, copie `.env.example` para `.env` se ainda não
existir e ajuste as configurações. Na raiz do projeto:

```sh
docker compose up -d --build orquestrador-saga ms-solicitacoes ms-agendamentos ms-pagamentos
docker compose logs -f orquestrador-saga ms-pagamentos
```

Os bancos e o RabbitMQ sobem como dependências. Nenhum desses quatro serviços
publica porta no host; continuam somente em `internal_net`.

Em outro terminal, execute a demonstração dentro dessa rede:

```powershell
Get-Content -Raw scripts/demo-frente2.py | docker compose exec -T orquestrador-saga python -
```

Em Bash:

```sh
docker compose exec -T orquestrador-saga python - < scripts/demo-frente2.py
```

O roteiro cria uma solicitação e orçamento reais, aceita com `pm_tok_recusado`,
aguarda `COMPENSADA` e verifica que não há reserva ativa. Em seguida contrata o
mesmo prestador no mesmo horário com `pm_tok_ok`, aguardando `CONCLUIDA` e
`CONFIRMADA`. Cada aceite é repetido com a mesma `Idempotency-Key` para conferir
que retorna a mesma SAGA. A demo usa headers de identidade internos e não passa
pelo Kong. Não envie dados reais de cartão.

Para acompanhar falhas, os logs do orquestrador registram `sagaId`, etapa, status
e `correlationId`. O pagamento recusa também qualquer valor **maior que 500000**
centavos. O limite de 500000 é aceito com um token diferente do token de recusa.

## Contratos novos

Todos os corpos e respostas são camelCase, salvo o contrato de repasses já
esperado pelo BFF. Exemplos completos podem ser consultados em `/docs` de cada
serviço dentro da rede interna.

| Serviço | Endpoint | Função |
|---|---|---|
| Solicitações | `POST /v1/solicitacoes` | Cria solicitação do `X-User-Id`, perfil contratante |
| Solicitações | `GET /v1/solicitacoes/{id}` | Estado da solicitação (com `sagaId`) e HATEOAS |
| Solicitações | `POST /v1/solicitacoes/{id}/orcamentos` | Orçamento do prestador autenticado |
| Solicitações | `GET /v1/solicitacoes/{id}/orcamentos` | Lista do contratante |
| Solicitações | `GET /v1/orcamentos/{id}` | Orçamento e ações permitidas |
| Solicitações | `POST /v1/orcamentos/{id}/recusa` | Recusa de orçamento |
| Orquestrador | `POST /v1/orcamentos/{id}/aprovacao` | `202`, exige `Idempotency-Key` (via Kong: `POST /v1/contratante/orcamentos/{id}/aprovacao`) |
| Orquestrador | `GET /v1/sagas/{id}` | Andamento da SAGA (lido pelo BFF) |
| Solicitações | `POST /v1/orcamentos/{id}/contratacao` | Interno, chamado pelo orquestrador: valida dono e orçamento e trava a solicitação |
| Solicitações | `POST /v1/orcamentos/{id}/contratacao/confirmacao` | Interno: solicitação `CONFIRMADA` |
| Solicitações | `POST /v1/orcamentos/{id}/contratacao/cancelamento` | Interno (compensação): volta a `AGUARDANDO_ACEITE` |
| Agendamentos | `POST /v1/reservas` | Reserva por `sagaId`, com `inicio` e `fim` |
| Agendamentos | `POST /v1/reservas/{id}/confirmacao` | Confirma reserva |
| Agendamentos | `POST /v1/reservas/{id}/liberacao` | `LiberarReserva`, idempotente |
| Agendamentos | `GET /v1/agendamentos?solicitacao_id=` | Reservas ativas |
| Pagamentos | `POST /v1/pagamentos` | `sagaId`, `solicitacaoId`, `valorCentavos`, `meioPagamentoId` |
| Pagamentos | `GET /v1/pagamentos/por-saga/{id}` | Conciliação após timeout |
| Pagamentos | `POST /v1/pagamentos/{id}/estorno` | Estorno simulado idempotente |
| Pagamentos | `GET /v1/repasses?solicitacao_id=` | Bruto, taxa e líquido dos aprovados |
| Todos | `GET /health`, `GET /ready` | Processo vivo e conexão ao banco |

O orçamento tem `duracaoMinutos` opcional (60 por padrão, até 1440) e validade
padrão de sete dias. Datas de comandos exigem fuso horário. O início escolhido
deve estar no futuro. Intervalos são semiabertos: `[inicio, fim)`, permitindo
atendimentos consecutivos sem sobreposição. `prazoEstimadoDias` é informativo;
não representa uma janela exata de disponibilidade. A taxa da demo é 10%, com
arredondamento para baixo em centavos. Nenhum token é exposto em consulta ou evento.

## Garantias e recuperação

- Aprovação persiste a SAGA antes do `202`. A chave é isolada por contratante;
  sua reutilização com outro corpo/orçamento retorna `409`.
- Advisory locks transacionais no PostgreSQL serializam aceites por solicitação,
  reservas por prestador e pagamentos por SAGA. Reservas e cobranças têm
  `sagaId` único. Horários conflitantes não iniciam cobrança.
- O worker retoma etapas do banco com `FOR UPDATE SKIP LOCKED`. Falhas de HTTP
  têm backoff de até 60s. O timeout padrão é 3s. Uma etapa confirmada remotamente
  pode ser repetida após crash sem duplicar o efeito.
- Timeout ao cobrar mantém a reserva. O próximo tick consulta o pagamento pela
  SAGA antes de repetir o comando. O resultado final chega pelo evento durável.
- Pagamento e outbox são gravados na mesma transação. O relay confirma publicação
  no broker antes de marcar o registro; entrega é **pelo menos uma vez**.
- Tanto produtor quanto consumidor declaram a fila antes de publicar/consumir,
  evitando perder eventos quando o orquestrador ainda não está conectado.
- Inbox e resultado da SAGA são persistidos juntos antes do ACK. Duplicatas não
  repetem efeitos. Mensagens inválidas vão à DLQ; falha de banco provoca reentrega.
- Recusa leva a `COMPENSACAO_PENDENTE`, `LIBERAR` e `CANCELAR_SOLICITACAO`. Só após a resposta da agenda e do ms-solicitacoes
  a SAGA vira `COMPENSADA`. Nova tentativa usa outra chave de idempotência.
- Se uma reserva não puder ser confirmada definitivamente (`404`/`409`), o
  orquestrador estorna primeiro e libera depois. Falhas transitórias são repetidas.
- Não há expiração automática de reservas: não se libera uma vaga enquanto o
  resultado financeiro pode ser desconhecido. Falhas permanentes de configuração
  exigem intervenção; o estado continua persistido sem anunciar sucesso indevido.

Exchange: `resolvelar.events`, topic durável. Fila:
`resolvelar.orquestrador.pagamentos` (consumida pelo `orquestrador-saga`), vinculada a `PagamentoAprovado` e
`PagamentoRecusado`. DLX: `resolvelar.events.dlx`; DLQ:
`resolvelar.orquestrador.pagamentos.dlq`. Mensagens persistentes; envelope conforme
`ARCHITECTURE.md`. A correlação também segue na propriedade AMQP `correlation_id`.

O esquema é inicializado com `SQLModel.metadata.create_all` em banco vazio;
alterações futuras de esquema precisarão de migrações. As funções `core.py` são
copiadas nos quatro contextos de build; `broker.py`, no `ms-pagamentos` e no `orquestrador-saga`.

## Testes e limites da validação

```sh
python -m venv .venv-frente2
# Windows:
.venv-frente2/Scripts/python -m pip install -r services/tests-frente2/requirements.txt
.venv-frente2/Scripts/python -m pytest services/tests-frente2 -q
```

Os testes locais exercitam os handlers dos três serviços, cada um com seu banco
SQLite, transporte HTTP em memória e publicação AMQP simulada. Cobrem sucesso,
recusa, limites monetários, idempotência, autorização, sobreposição de horários,
atomicidade da outbox, confirmação de publicação, eventos duplicados, timeout
após commit, repetição de compensação e estorno antes de liberar.

Resultado local: **17 testes passaram**, incluindo conferência dos contratos do
Compose. Compilação Python também passou. O runtime
local foi Python 3.14; o build Docker mantém Python 3.12 do template. Houve um
aviso de depreciação do transporte `httpx` no TestClient da versão instalada de
Starlette, sem falhas nos testes.

Eles **não substituem** a execução da demo com PostgreSQL/RabbitMQ reais nem
validam os locks concorrentes do PostgreSQL.
Docker não estava disponível no ambiente da implementação.

Integração pendente com a Frente 1: o BFF contratante desta base não registra as
rotas de criação e acompanhamento de solicitações e a rota de comparação de
orçamentos. Os links retornados aqui são os contratos internos `/v1/...`;
a exposição/tradução pelo BFF deve ser combinada com o responsável. Esses
arquivos não foram alterados por solicitação do usuário.
