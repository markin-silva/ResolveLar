<p align="center">
  <img src="imagens/logotrabalho.png" width="350">
</p>

## Equipe
* Marcus Vinícius Alves Silva
* Maria Clara Miguel Silva
* João Paulo Souza Selvati
* Luiza Oliveira de Souza Garcia

## 1. Visão Geral da Startup

<p>
  <img src="imagens/2xx.png" width="300" align="left">

  A ResolveLar é uma plataforma digital que conecta pessoas que precisam de serviços de manutenção residencial a profissionais disponíveis para realizá-los. O aplicativo reúne diferentes tipos de serviço em um único ambiente, permitindo que o cliente encontre profissionais, solicite atendimento, receba orçamentos, escolha um prestador, agende o serviço e avalie o atendimento.
</p>

<br clear="left">


## 2. Problema e Motivação

<p>
  <img src="imagens/1..png" width="300" align="left">

  Encontrar um profissional para resolver um problema dentro de casa ainda depende, muitas vezes, de indicações informais, grupos de mensagens ou buscas dispersas na internet. Quando surge um problema como um chuveiro queimado ou um vazamento, o contratante precisa descobrir quem presta o serviço, se atende a região, qual a disponibilidade, o custo e a confiabilidade do profissional. Do outro lado, diversos prestadores autônomos precisam encontrar clientes e construir uma reputação digital.
</p>

<p>
  Esse cenário de desorganização ocorre em um mercado em plena transformação digital. Segundo o módulo temático "Trabalho por Meio de Plataformas Digitais" da PNAD Contínua, do IBGE, cerca de 1,7 milhão de pessoas trabalhavam por meio de plataformas digitais de serviços no 3º trimestre de 2024, um crescimento de 25,4% em relação a 2022 [1]. Dentro desse total, o segmento de "serviços gerais ou profissionais" — categoria em que se enquadra a manutenção residencial — foi o que proporcionalmente mais cresceu no período, com expansão de 52,1% [1], reforçando a relevância do domínio escolhido pela ResolveLar.
</p>

<p>
  O levantamento "Sebrae em Dados" confirma o tamanho expressivo do mercado de manutenção residencial, historicamente fragmentado [2]. Já as diretrizes de apoio ao microempreendedor do Sebrae alertam para os impactos da vulnerabilidade na gestão de pequenos negócios [3], destacando a dificuldade de gerir a própria carteira de clientes de forma segura.
</p>

<p>
  No âmbito acadêmico, Abílio, Amorim e Grohmann (2021) discutem como a plataformização do trabalho reconfigura a informalidade brasileira, fazendo emergir uma "novíssima informalidade" marcada pela subordinação de trabalhadores informais a empresas e pela perda de formas estáveis de organização produtiva [4]. A ResolveLar nasce para atuar como um contraponto a essa precarização, buscando reduzir a distância entre quem precisa de um serviço e quem possui a capacidade de realizá-lo, garantindo ao prestador a construção de um histórico digital sólido e uma melhor gestão de sua agenda.
</p>

<br clear="left">

## 3. Impacto Social Esperado

<p>
  <img src="imagens/6..png" width="300" align="left">

  A proposta atua principalmente em dois aspectos de impacto. O primeiro é a geração de oportunidades de trabalho para prestadores de serviços, especialmente profissionais autônomos que possuem conhecimento técnico, mas têm dificuldade para encontrar novos clientes. O segundo é a facilitação do acesso da população a serviços de manutenção residencial, centralizando busca, disponibilidade, orçamento e reputação em uma única plataforma.
</p>

<p><strong>Quem é beneficiado:</strong></p>

<ul>
  <li><strong>Contratantes:</strong> Pessoas que necessitam de manutenção ou pequenos serviços em suas residências e querem encontrar profissionais disponíveis de maneira rápida e organizada.</li>
  <li><strong>Prestadores:</strong> Profissionais autônomos ou pequenos prestadores de serviço que desejam aumentar sua exposição, encontrar clientes e organizar seus atendimentos.</li>
</ul>

<p><strong>Como o impacto será medido (Indicadores):</strong></p>

<p>
  O impacto poderá ser acompanhado por indicadores como quantidade de profissionais ativos, quantidade de serviços concluídos e quantidade de solicitações atendidas. Também serão avaliados o tempo médio entre solicitação e contratação e a avaliação média dos serviços.
</p>

<br clear="left">

## 4. Esboço da Solução

<p>
A ResolveLar não será apenas um catálogo de profissionais, acompanhando todo o ciclo da contratação.
</p>

<p><strong>Jornada de Uso:</strong></p>

<ol>
  <li>O cliente descreve o problema, informa a localização, a categoria do serviço (a partir de uma lista) e uma preferência de data.</li>
  <li>A plataforma apresenta os profissionais compatíveis com aquela categoria que atendem a região informada.</li>
  <li>O cliente consulta o perfil dos profissionais (avaliações, serviços realizados) e solicita orçamento a um ou mais prestadores.</li>
  <li>Cada prestador que recebe a solicitação analisa o serviço e envia sua proposta, com valor e prazo estimados.</li>
  <li>O cliente escolhe uma das propostas recebidas; a plataforma verifica a disponibilidade do profissional e confirma o agendamento.</li>
  <li>Ao concluir o serviço, o prestador confirma a finalização da execução; em seguida, o cliente confirma o recebimento, e ambos podem avaliar a experiência.</li>
</ol>

<p align="center">
  <img src="imagens/7..png" width="1000">
</p>

## 5. Esboço da Arquitetura

A ResolveLar será estruturada utilizando uma arquitetura baseada em
microsserviços, com API Gateway, clientes distintos para contratantes
e prestadores e bancos de dados independentes por serviço.

➡️ Documentação de arquitetura em [`docs/`](docs/):
- [01 — Decomposição em microsserviços e banco de dados](docs/01-decomposicao-e-dados.md)
- [02 — Gateway e BFF](docs/02-gateway-e-bff.md)
- [03 — SAGA orquestrada (aceite de orçamento)](docs/03-saga-orquestrada.md)
- [04 — REST, HATEOAS e CQRS](docs/04-rest-e-cqrs.md)

## 6. Como o projeto funciona

```
Navegador ──► Kong :8000 ──► BFF (contratante ou prestador) ──► microsserviços ──► PostgreSQL (um por serviço)
                 │                                                     │
              Redis                                     RabbitMQ (eventos)
           (rate limit)
```

- **Kong** (API Gateway) é a única porta de entrada. Remove o prefixo `/v1/contratante` ou `/v1/prestador`, gera o `X-Correlation-Id` e aplica CORS e rate limit.
- **BFFs** (`bff-contratante`, `bff-prestador`) montam a resposta de cada tela. Não têm banco próprio.
- **Microsserviços** são donos dos dados: `ms-prestadores`, `ms-solicitacoes` (orquestrador da SAGA), `ms-agendamentos`, `ms-pagamentos` e `ms-avaliacoes`.
- **Aceite de orçamento (SAGA):** `POST /v1/orcamentos/{id}/aprovacao` responde `202`. O `ms-solicitacoes` reserva o horário no `ms-agendamentos` e cobra no `ms-pagamentos`. Se o pagamento for recusado, a reserva é liberada (compensação). O resultado chega por evento no RabbitMQ.
- **CQRS:** o `ms-prestadores` grava no banco de escrita e um projetor atualiza o banco de leitura desnormalizado, usado nas buscas.

Detalhes e contratos: [`.ai-memory/ARCHITECTURE.md`](.ai-memory/ARCHITECTURE.md).

### Estado atual

| Parte | Situação |
|---|---|
| Infraestrutura (Kong, Redis, RabbitMQ, 6× PostgreSQL) | Pronta, sobe com `docker compose up` |
| Kong: JWT por perfil, rate limit por usuário, CORS, correlation-id | Pronto |
| Login com usuários de demonstração (`ms-auth`) | Pronto: 3 contratantes e 11 prestadores, senha única de teste |
| Microsserviços (`ms-*`): prestadores (CQRS), solicitações (SAGA), agendamentos, pagamentos, avaliações, triagem IA | Prontos |
| `bff-contratante` e `bff-prestador` | Prontos |
| Frontends (`web-contratante` :3001, `web-prestador` :3002) | Prontos, com login e fluxos completos |

Acompanhe o andamento em [`.ai-memory/PROJECT_STATE.md`](.ai-memory/PROJECT_STATE.md).

## 7. Como rodar

### Pré-requisitos
- Docker e Docker Compose v2 (`docker compose version`)
- `curl` (para os testes abaixo)

### Primeira vez

```bash
git clone <url-do-repositorio> ResolveLar
cd ResolveLar
cp .env.example .env     # cria o arquivo de configuração local
docker compose up -d --build
docker compose ps        # todos devem aparecer "healthy" (leva ~1 min na primeira vez)
```

Abra os dois apps no navegador e entre com um dos usuários de demonstração (ver [`docs/07-passo-a-passo-testes.md`](docs/07-passo-a-passo-testes.md)):

- Contratante: <http://localhost:3001>
- Profissional: <http://localhost:3002>

Senha de todos os usuários: a `DEMO_PASSWORD` do `.env` (no `.env.example`, `resolvelar123`).

O `.env` é o arquivo com as senhas locais. Ele **não vai para o Git** (está no `.gitignore`). Os valores de `.env.example` são placeholders de teste: troque-os se for usar o projeto fora da sala de aula.

### Testar que está funcionando

Entre pela API com um usuário de demonstração (o `ms-auth` emite o token que o Kong valida):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"usuario":"mariana","senha":"resolvelar123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/contratante/solicitacoes   # 200, os pedidos da Mariana
curl -i http://localhost:8000/v1/contratante/prestadores                                    # 401 (sem token)
curl -si -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/prestador/agenda | head -1  # 403 (perfil errado)

# Infraestrutura
docker compose exec redis redis-cli ping                       # PONG
docker compose exec rabbitmq rabbitmq-diagnostics -q ping      # Ping succeeded
```

> **Limite de login:** são 5 tentativas por minuto por IP em `POST /v1/auth/login`. Se aparecer "muitas tentativas", espere um minuto.

> **Painel do RabbitMQ:** a porta 15672 **não está publicada** no host. Para usá-lo, adicione `"127.0.0.1:15672:15672"` à seção `ports` do serviço `rabbitmq` no `docker-compose.yml`.

### Dados de exemplo (mock) nos BFFs

Com `ENABLE_UPSTREAM_MOCK=true` (padrão do `.env.example`), se um microsserviço **não estiver no ar** o BFF devolve payloads de exemplo e marca a resposta com `X-Mock-Upstream: true`. Com os serviços rodando, isso não acontece. Para testar falhas de verdade, pare um serviço (`docker compose stop ms-prestadores`) e veja o que a tela mostra. Com `false`, falhas viram `503` (dado essencial) ou o bloco é omitido (dado opcional).

### Testar um microsserviço (template)

Todo serviço novo começa a partir de `services/_template-fastapi`:

```bash
cd services/_template-fastapi
docker build -t resolvelar/template-fastapi:test .
docker run -d --name tpl -p 127.0.0.1:8100:8000 resolvelar/template-fastapi:test
curl -s http://127.0.0.1:8100/health      # {"status":"ok",...}
docker rm -f tpl
```

### Parar

```bash
docker compose down       # para e mantém os dados dos bancos
docker compose down -v    # para e APAGA os dados (zera os bancos)
```

### Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `port is already allocated` na 8000 | Outro programa usa a porta 8000 | Pare o outro programa ou mude a porta em `docker-compose.yml` |
| Contêiner `unhealthy` | Banco ou broker ainda iniciando | Aguarde 30s e rode `docker compose ps` de novo; se persistir, `docker compose logs <servico>` |
| `DATABASE_URL não configurada` | Serviço sem variável de ambiente | Confira o `.env` e o bloco `environment` do serviço no compose |
| `401` mesmo com token | Token expirado (24h) ou segredo diferente | Gere outro: `python3 scripts/generate_jwt.py` |
| `429` ao testar | Rate limit (10/h criar solicitação, 30/h criar orçamento) | Zere os contadores: `docker compose exec redis redis-cli FLUSHALL` |
| Editou o `gateway/kong.tpl.yml` e nada mudou | O Kong só lê o arquivo ao iniciar | `docker compose up -d --force-recreate kong` |
| Mudou a senha no `.env` e o banco não aceita | Volume já criado com a senha antiga | `docker compose down -v` (apaga os dados) e suba de novo |

## 8. Estrutura do repositório

| Caminho | Conteúdo |
|---|---|
| `docker-compose.yml` | Infraestrutura local (Kong, Redis, RabbitMQ, bancos) |
| `.env.example` | Variáveis de ambiente (copiar para `.env`) |
| `gateway/kong.tpl.yml` | Rotas, JWT/ACL, rate limit e plugins do Kong (modo declarativo). É um template: o `kong.yml` é gerado na subida com o `JWT_SECRET` do `.env` |
| `services/bff-contratante/`, `services/bff-prestador/` | BFFs (FastAPI) |
| `scripts/` | `generate_jwt.py` (tokens de teste, uso avançado), `demo-frente2.py` (demo da SAGA) |
| `services/_template-fastapi/` | Base para todos os serviços Python |
| `docs/` | Documentação de arquitetura (seções 1 a 4) |
| `.ai-memory/` | Memória compartilhada do projeto: arquitetura, estado, decisões |
| `.github/copilot-instructions.md`, `.cursorrules` | Instruções para agentes de IA no VS Code |

## 9. Como contribuir

1. Antes de codar, leia `.ai-memory/ARCHITECTURE.md`, `PROJECT_STATE.md` e `DECISIONS_LOG.md`.
2. Nomes de hosts, portas, filas e rotas devem seguir o `ARCHITECTURE.md`. Mudança de contrato, endpoint, evento ou variável de ambiente vai para o `DECISIONS_LOG.md`.
3. Nunca commite credenciais. Use variáveis de ambiente (`.env` local).
4. Ao concluir uma tarefa, atualize o `PROJECT_STATE.md`.
5. Commits no padrão [Conventional Commits](https://www.conventionalcommits.org/), em inglês (ex.: `feat(pagamentos): implement transactional outbox relay`).

## Referências

1. IBGE. Trabalho por Meio de Plataformas Digitais 2024 (PNAD Contínua, 3º trimestre de 2024). Rio de Janeiro: IBGE, 2025. Disponível em: https://agenciadenoticias.ibge.gov.br/media/com_mediaibge/arquivos/59722d4ac24bd853f52f54f12b9514f7.pdf
2. SEBRAE. Sebrae em Dados: Serviços de Manutenções Residenciais. 2022. Disponível em: https://sebraepr.com.br/comunidade/artigo/sebrae-em-dados-servicos-de-manutencoes-residenciais
3. SEBRAE. Impactos da Pejotização: Guia Completo para Micro e Pequenos Empreendedores. 2025. Disponível em: https://sebraepr.com.br/impulsiona/impactos-da-pejotizacao-guia-completo-para-micro-e-pequenos-empreendedores/
4. ABÍLIO, L. C.; AMORIM, H.; GROHMANN, R. Uberização e plataformização do trabalho no Brasil: conceitos, processos e formas. Sociologias, Porto Alegre, 2021. Disponível em: https://seer.ufrgs.br/index.php/sociologias/article/view/116484
