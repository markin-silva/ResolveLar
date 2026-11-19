# Instruções para agentes — ResolveLar

Projeto da disciplina GCC129 (Sistemas Distribuídos). Siga estas regras em qualquer tarefa.

1. **Antes de escrever qualquer código**, leia:
   - `.ai-memory/ARCHITECTURE.md` (stack, portas, hosts, contratos REST, eventos)
   - `.ai-memory/PROJECT_STATE.md` (o que está pronto/em andamento)
   - `.ai-memory/DECISIONS_LOG.md` (ajustes de contrato)
2. Nunca invente hosts, filas ou rotas que contrariem `ARCHITECTURE.md`. Novo endpoint, evento ou variável de ambiente deve ser registrado em `DECISIONS_LOG.md`.
3. **Nunca coloque credenciais hardcoded.** Use sempre variáveis de ambiente, mapeadas em `.env.example`, `docker-compose.yml` e ConfigMaps/Secrets do Kubernetes.
4. MVP pragmático: FastAPI + SQLModel + Pydantic, sem abstrações desnecessárias. Chamadas HTTP entre serviços com timeout curto (3s). Consumidores RabbitMQ idempotentes. Todo serviço com `Dockerfile` multi-stage.
5. **Antes de finalizar qualquer tarefa**, atualize `.ai-memory/PROJECT_STATE.md` (item concluído, arquivos/rotas criados) e, se houve mudança de contrato, `.ai-memory/DECISIONS_LOG.md` (entrada datada).
6. Ao final, sugira uma mensagem de commit em **Conventional Commits, em inglês** (ex.: `feat(pagamentos): implement transactional outbox relay`) e lembre de usar `Co-authored-by:` se houve trabalho em par.
