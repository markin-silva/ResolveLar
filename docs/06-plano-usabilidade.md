# Plano: usabilidade e fluxo de contratante e prestador

Status: **aprovado, em execução** (Fase 0 concluída). Decisões do usuário em 2026-11-24.

## Decisões aprovadas

| Tema | Decisão |
|---|---|
| Login | **Usuários fixos e pré-cadastrados**, com tela "Entrar" e `POST /v1/auth/login`. Sem registro de contas novas e sem `ms-identidade` completo. |
| Pedido ao prestador | Por **categoria e cidade** (fila de demandas). Sem convite direto. |
| Conclusão do serviço | **Fora do escopo.** |
| Avaliação | Só o **dono** da solicitação avalia, com a solicitação `CONFIRMADA`. O `prestadorId` vem da própria solicitação, não do corpo. |
| Testes de frontend | Não entram no repositório. |

## Requisitos do trabalho que o plano preserva

Clientes só falam com o Kong · REST com HATEOAS e RFC 7807 · valores em centavos · CQRS no `ms-prestadores` · SAGA com compensação e `Idempotency-Key` · triagem com RAG e fallback · dois BFFs distintos · sem credenciais no código · só Docker.

## Diagnóstico

- O prestador só abre uma solicitação se souber o ID, e leva 403 antes de ser escolhido.
- O contratante não tem "meus pedidos" e precisa copiar IDs.
- A lista de profissionais não se liga ao pedido.
- O horário da aprovação é sempre "agora + 24 h" (gera conflito de agenda).
- A avaliação abre cedo demais e o `ms-avaliacoes` aceita qualquer solicitação.
- Os tokens são colados à mão e há só dois usuários de teste.

Boa parte já estava **prevista nos documentos** e não foi entregue: `GET /v1/solicitacoes?status=` (docs/04), "fila de solicitações" e "agenda" do prestador (docs/02) e `POST /auth/login` com 5/min por IP (docs/02).

## Fluxo alvo

**Contratante:** entra → "Meus pedidos" → "Novo pedido" (descrever, triagem opcional, criar e já abrir o pedido) → compara orçamentos → aprova (data e hora, cartão, acompanha a SAGA) → avalia.

**Prestador:** entra → "Novas solicitações" (categorias e cidade dele) → vê a demanda **antes** de orçar (endereço e contato só após a confirmação) → "Meus orçamentos", "Agenda" e "Ganhos" (bruto, taxa e líquido).

## Mudanças por camada

| Camada | Mudança |
|---|---|
| Kong | Um consumer por perfil; `pre-function` copia o `sub` do JWT para `X-User-Id`; rate limit por `X-User-Id`; rota pública `/v1/auth/login` (5/min por IP); segredo do JWT vindo do ambiente |
| Novo serviço `auth` | `POST /v1/auth/login` (usuário e senha de seed), emite JWT HS256 com o segredo do ambiente |
| `ms-solicitacoes` | `GET /v1/solicitacoes` (do contratante; ou fila por `categoria`/`cidade`/`status` para o prestador); `GET /v1/orcamentos?prestador_id=` |
| `ms-agendamentos` | `GET /v1/agendamentos?prestador_id=&de=&ate=` |
| `ms-pagamentos` | `GET /v1/repasses?prestador_id=` |
| `ms-avaliacoes` | Valida dono e status da solicitação; `prestadorId` vem da solicitação |
| `bff-contratante` | `GET /solicitacoes`; avaliação com validação; lê `X-User-Id` |
| `bff-prestador` | `GET /solicitacoes` (fila), `GET /solicitacoes/{id}` (visão limitada), `/orcamentos`, `/agenda`, `/ganhos`; lê `X-User-Id` |
| Frontends | Tela de entrada com usuários de teste, React Router, listas, estados de carregamento, vazio e erro, mensagens claras para 403/409/422 |

## Fases

| Fase | Entrega | Verificação |
|---|---|---|
| 0 | Validar Kong com usuários fixos (feita) | Kong descartável |
| 1 | Backend: listagens, validação das avaliações, fila do prestador | `curl` via Kong |
| 2 | Auth fixo + Kong por perfil + segredo do ambiente | Login dos usuários e rate limit por usuário |
| 3 | Frontends novos | Navegador |
| 4 | Documentação, `DECISIONS_LOG`, `PROJECT_STATE`, passo a passo para os integrantes | Script E2E |

## Resultado da Fase 0 (Kong)

Validado em um Kong 3.6 descartável:

1. **Um consumer por perfil funciona.** Dois usuários com o mesmo `iss` chegam ao upstream com `X-User-Id` distinto (o `sub` do token).
2. **Rate limit por usuário funciona** com `limit_by: header` em `X-User-Id`: estourar o limite de um usuário não afeta o outro.
3. **Sem brecha de identidade.** Um `X-User-Id` falso enviado pelo cliente é sobrescrito; token com assinatura falsa recebe 401 e não consome limite de ninguém.
4. **Segredo fora do `kong.yml`:** o vault `env` do Kong 3.6 **não** resolveu o segredo da credencial JWT (retornou 401). A saída que funcionou foi um template com `__JWT_SECRET__` substituído por `sed` no entrypoint do contêiner (a imagem do Kong **não tem `envsubst`**, só `sed` e `awk`).

## Riscos e pontos de atenção

- O `docs/01` rejeitou um "MS Usuários" genérico, e o `docs/02` diz que o Kong não emite tokens. O serviço de `auth` guarda só credenciais de seed, sem dados de domínio, o que respeita o espírito dos dois textos. Vale confirmar com o professor.
- A fila do prestador é uma consulta em `db-solicitacoes`, não uma projeção CQRS. É aceitável para o MVP.
- Um prestador de seed ainda depende da consistência eventual do CQRS.
