# Pipeline de Desenvolvimento Automático

Pipeline que lê cards de um quadro de projeto (GitHub Projects, Jira ou Trello), e para cada card que está em uma coluna com um **Agente** de IA associado, cria um **Job** que executa uma CLI de IA (Antigravity, Claude, Codex ou Gemini) no diretório local do projeto. Possui interface web (FastAPI + HTMX) e CLI (Typer).

> Documentação detalhada de arquitetura e decisões: [PROJETO.md](PROJETO.md).

## Arquitetura (resumo)

Arquitetura em camadas, com portas e adaptadores:

- **`domain/`** — entidades, exceções, registries e *ports* (`CliProvider`, `ProjectBoardReader/Writer`, repositórios, `UnitOfWork`).
- **`application/`** — serviços de caso de uso:
  - `PipelineOrchestrator`: busca cards do quadro, sincroniza, cria jobs pendentes e cancela os obsoletos.
  - `SyncService`: compara cards remotos com os locais (via hash do conteúdo) e gera `CardEvent`.
  - `JobRunnerService`: executa um job chamando a CLI de IA do agente.
  - `ModelCatalogService`: sincroniza o catálogo de modelos das CLIs instaladas.
- **`adapters/`** — implementações concretas: `cli_providers` (agy, claude, codex, gemini), `project_providers` (GitHub, Jira, Trello) e `db` (SQLModel, repositórios, UoW, seed).
- **`web/`** — interface FastAPI + Jinja2 + HTMX (projetos, agentes, colunas, jobs, configurações).
- **`cli.py`** — comandos Typer.
- **`bootstrap.py`** — cria e preenche os registries de provedores.

### Documentação detalhada

- **Domínio & Contratos**: [entities](docs/entities.md) · [exceptions](docs/exceptions.md) · [registry](docs/registry.md) · [ports](docs/ports.md) · [contracts](docs/contracts.md) · [providers](docs/providers.md)
- **Banco de Dados (`adapters/db`)**: [visão geral](docs/db/README.md) · [engine](docs/db/engine.md) · [orm_models](docs/db/orm_models.md) · [repositories](docs/db/repositories.md) · [uow](docs/db/uow.md) · [seed](docs/db/seed.md)

### Fluxo

1. O **Celery Beat** dispara periodicamente a sincronização da pipeline (ou ela pode ser disparada manualmente via CLI / Web em Projetos).
2. O provedor de quadro busca os cards do projeto e `SyncService` atualiza `Card` e registra `CardEvent`.
3. Para cada card numa `FlowColumn` ativa com agente, cria-se um `Job` pendente (se não houver um ativo) e a task é enviada ao **Celery**.
4. Jobs pendentes cujo card saiu da coluna (ou foi removido) são cancelados (e revogados no Celery).
5. O **Celery Worker** executa o job via `JobRunnerService` com a CLI e o modelo do agente, atualizando o status do processo em tempo real na interface web.
6. O timeout das tasks do Celery (`soft_time_limit` / `time_limit`) é calculado automaticamente a partir de `CLI_TIMEOUT_SECONDS` somado a uma margem operacional (`CELERY_TIMEOUT_OVERHEAD_SECONDS` e `CELERY_HARD_TIMEOUT_GRACE_SECONDS`).

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Requer Python ≥ 3.11. Variáveis em [.env.example](.env.example) (banco, host/porta, timeout da CLI e credenciais dos provedores).

## Uso

```bash
# 1. Suba o broker Redis (ex. via Docker)
docker compose up -d

# 2. Inicialize o banco e catálogo de modelos
pipeline db init        # cria o banco e dados iniciais
pipeline models sync    # sincroniza modelos das CLIs instaladas

# 3. Inicie o worker e o scheduler (Beat) do Celery e a interface Web
pipeline celery worker  # consome e executa os jobs em segundo plano
pipeline celery beat    # agenda a execução automática periódica da pipeline
pipeline web            # inicia a interface web (apenas acompanhamento e gestão da fila)

# Comandos auxiliares
pipeline celery status  # verifica broker, workers online e timeouts configurados
pipeline run            # dispara sincronização manual e envia jobs ao Celery
pipeline jobs list      # lista jobs
pipeline jobs run       # envia jobs pendentes para o Celery
```

Use `pipeline <comando> --help` para ver as opções de cada comando.

## Testes

```bash
pytest
```
