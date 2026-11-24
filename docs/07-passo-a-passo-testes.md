# Passo a passo para testar o ResolveLar

Para quem vai testar o projeto. Não é preciso criar conta: todos os usuários já existem.

## 1. Subir o projeto (uma vez)

```bash
git clone <url-do-repositorio> ResolveLar
cd ResolveLar
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Espere todos os serviços aparecerem como **healthy** (cerca de 1 a 2 minutos na primeira vez).

Se algo não subir: `docker compose logs <nome-do-serviço>` mostra o erro.

## 2. Endereços

| O que | Endereço |
|---|---|
| App do **contratante** (quem contrata) | <http://localhost:3001> |
| App do **profissional** (quem presta o serviço) | <http://localhost:3002> |

## 3. Usuários e senha

**Senha de todos: `resolvelar123`**

| Quem | Usuário na tela | Perfil |
|---|---|---|
| Mariana Alves | Mariana Alves | Contratante |
| Rafael Costa | Rafael Costa | Contratante |
| Juliana Ramos | Juliana Ramos | Contratante |
| Carlos Silva | Carlos Silva | Profissional · eletricista e instalador |
| Ana Souza | Ana Souza | Profissional · eletricista |
| João Pereira | João Pereira | Profissional · encanador |
| Hidráulica Rocha | Hidráulica Rocha | Profissional · encanador e gás |
| Marcos Gás & Cia | Marcos Gás & Cia | Profissional · técnico de gás |
| Pedro Construções | Pedro Construções | Profissional · pedreiro |
| Lúcia Pinturas | Lúcia Pinturas | Profissional · pintora |
| Chaveiro 24h Lavras | Chaveiro 24h Lavras | Profissional · chaveiro |
| Marcenaria Oliveira | Marcenaria Oliveira | Profissional · marceneiro |
| Rafael Refrigeração | Rafael Refrigeração | Profissional · instalador |
| Encanador BH | Encanador BH | Profissional · encanador em Belo Horizonte |

> Use o app do **contratante** com os usuários da primeira parte, e o app do **profissional** com os da segunda.

**Atenção ao login:** são **5 tentativas por minuto**. Se aparecer "muitas tentativas", espere um minuto.

## 4. Fluxo completo (cerca de 10 minutos)

Este roteiro percorre todo o sistema. Faça na ordem.

### Parte A: o contratante pede um serviço

No app **contratante** (`localhost:3001`):

1. Escolha **Rafael Costa** e entre com a senha.
   - **Esperado:** abre "Meus pedidos".
2. Clique em **Novo pedido**.
3. Em "O que está acontecendo?", escreva algo como: *"A torneira da cozinha está pingando sem parar desde ontem"*.
4. (Opcional) Clique em **Analisar com o assistente**.
   - **Esperado:** aparece uma sugestão de categoria, orientações e a urgência.
5. Escolha a categoria **Encanamento**. Preencha CEP (ex.: `37200-000`), bairro (ex.: `Centro`) e rua (ex.: `Rua das Acácias, 45`).
6. Clique em **Criar pedido**.
   - **Esperado:** abre a página do pedido **sozinho**, com a mensagem "Pedido criado!" e o aviso de que ainda não há orçamentos.

### Parte B: o profissional vê a demanda e orça

No app **profissional** (`localhost:3002`) — **numa aba anônima** ou depois de sair da conta do contratante:

1. Escolha **João Pereira** (encanador) e entre.
   - **Esperado:** abre "Novas solicitações", com o pedido da Rafael na lista.
2. **Confira:** a lista mostra categoria, descrição e bairro, mas **não mostra a rua**.
3. Clique no pedido.
   - **Esperado:** mostra os detalhes e o formulário "Enviar orçamento". A rua **continua oculta**.
4. Preencha o valor (ex.: `95,50`), o prazo e o que está incluído. Clique em **Enviar orçamento**.
   - **Esperado:** mensagem de orçamento enviado.

### Parte C: o contratante escolhe e paga

De volta ao app **contratante**, na página do pedido:

1. Recarregue a página (F5).
   - **Esperado:** aparece o orçamento de **R$ 95,50**, com o nome do profissional e o botão **Aprovar**.
2. Em **Cartão**, escolha **Cartão recusado (teste)** e clique em **Aprovar**.
   - **Esperado:** aparece a mensagem de que o pagamento não foi concluído e a reserva foi liberada. O pedido volta a "Aguardando sua escolha".
3. Em **Cartão**, escolha **Cartão aprovado (teste)**. **Troque o dia ou o horário** (se repetir o horário anterior, o sistema recusa, porque já está reservado) e clique em **Aprovar**.
   - **Esperado:** aparece "Serviço confirmado" e o formulário de avaliação.
4. Escolha uma nota e clique em **Enviar avaliação**.
   - **Esperado:** mensagem de agradecimento.

### Parte D: o profissional acompanha o serviço

De volta ao app **profissional**, entrando como **João Pereira**:

1. Clique no mesmo pedido em "Novas solicitações" (ou em **Agenda**).
   - **Esperado:** agora aparecem o **endereço completo**, o **cliente** e o bloco **Quanto você recebe** (valor, taxa de 10% e líquido).
2. Abra **Agenda**: o horário do atendimento aparece, agrupado por dia.
3. Abra **Ganhos**: o serviço aparece no extrato, com o total.
4. Abra **Meus orçamentos**: o orçamento de R$ 95,50 aparece como aprovado.

## 5. Testes de isolamento (o sistema não deixa ver o que não é seu)

| Teste | Como | Resultado esperado |
|---|---|---|
| Outro contratante não vê o pedido | Entre como **Mariana** no app do contratante | A lista de Mariana **não** mostra o pedido do Rafael |
| Profissional de outra área não vê a demanda | Entre como **Carlos Silva** (eletricista) no app do profissional | A fila **não** mostra o pedido de encanamento |
| Profissional não abre tarefa de outro | Com Carlos, abra o endereço de uma demanda já confirmada com o João | Não aparece a rua nem o contato |
| Sem sessão | Abra <http://localhost:3001/> em aba anônima | Vai para a tela de entrada |
| Senha errada | Qualquer usuário, senha `errada` | Mensagem "Senha incorreta" |
| Sair | Clique em **Sair** | Volta para a tela de entrada |

## 6. Cenários de falha (opcionais, para ver a resiliência)

Estes testes param um serviço de propósito. **Reinicie depois** com `docker compose start <serviço>`.

| Serviço parado | Comando | O que deve acontecer |
|---|---|---|
| Assistente de IA | `docker compose stop ms-triagem` | A análise do pedido mostra erro, mas dá para criar o pedido normalmente |
| Cache Redis | `docker compose stop redis` | A triagem continua funcionando, sem cache |
| Catálogo de profissionais | `docker compose stop ms-prestadores` | A lista de profissionais mostra erro claro; o restante continua |

## 7. Algo deu errado?

| Sintoma | O que fazer |
|---|---|
| "Muitas tentativas" ao entrar | Espere 1 minuto. |
| "Sessão expirou" | Entre de novo. Os tokens valem 12 horas. |
| Tela em branco ou erro de conexão | Confira `docker compose ps`. Se algum serviço não estiver *healthy*, rode `docker compose logs <serviço>`. |
| "Horário indisponível" ao aprovar | Escolha outro dia ou horário. |
| Pedido ficou em "Confirmando…" por muito tempo | Atualize a página. Se continuar, avise quem organizou o teste. |

Ao reportar um problema, envie: o que você fez, o que esperava e o que apareceu (print da tela).

## 8. Para quem organiza o teste

- Os usuários e a senha vêm do `.env` (`DEMO_PASSWORD`). Para trocar a senha, edite o `.env` e rode `docker compose up -d --force-recreate ms-auth`.
- Para zerar os dados de teste (pedidos, reservas), apague os volumes: `docker compose down -v` e suba de novo. **Isso apaga tudo**, inclusive os pedidos criados.
