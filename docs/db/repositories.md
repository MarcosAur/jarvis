# Repositórios SQL

Implementado em [repositories.py](../../src/pipeline/adapters/db/repositories.py). Fornece as implementações concretas dos repositórios definidos em [domain/ports/repositories.py](../../src/pipeline/domain/ports/repositories.py) utilizando consultas SQLAlchemy / SQLModel sobre a `Session` ativa.

Todos os repositórios recebem a `Session` do SQLAlchemy no construtor e operam dentro da transação gerenciada pelo [Unit of Work](uow.md). Operações de mutação (`create`, `update`, `delete`) invocam `self.session.flush()` para garantir que IDs gerados e constraints sejam avaliados imediatamente.

---

## 1. `SqlSettingsRepository`

Gerencia o registro global de configurações (`AppSettings`, ID fixo 1).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get()` | `() -> AppSettings` | Retorna o registro `id=1`. Caso não exista, cria e persiste a configuração padrão inicial com flush. | - `JobRunnerService.run_job`<br>- `PipelineOrchestrator.run_for_project`<br>- Rotas web: `agents.py`, `projects.py`, `settings.py` |
| `update(...)` | `(default_cli_provider, active_project_provider, provider_settings) -> AppSettings` | Atualiza o CLI padrão, provedor de projeto ativo e o dicionário JSON de credenciais, atualizando `updated_at`. | - Rota web `POST /settings` ([settings.py](../../src/pipeline/web/routes/settings.py)) |

---

## 2. `SqlAgentRepository`

Gerencia as instâncias e diretrizes dos agentes autônomos (`Agent`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(agent_id)` | `(agent_id: int) -> Agent \| None` | Busca agente por chave primária. | - `JobRunnerService`<br>- `PipelineOrchestrator`<br>- Rotas web: `agents.py`, `columns.py`, `jobs.py`, `projects.py` |
| `get_by_name(name)` | `(name: str) -> Agent \| None` | Busca agente pelo nome único. | - `seed_database()` ([seed.py](seed.md)) |
| `list_all(active_only=False)` | `(active_only: bool) -> list[Agent]` | Lista agentes ordenados por nome, opcionalmente filtrando apenas os ativos (`active=True`). | - Rotas web: `agents.py`, `columns.py`, `jobs.py` |
| `create(name, cli_provider, ...)` | `(name, cli_provider, model_id, prompt_markdown, active=True) -> Agent` | Cria novo agente com timestamps UTC. | - `seed_database()`<br>- Rota web `POST /agents/new` |
| `update(agent_id, **kwargs)` | `(agent_id: int, **kwargs: Any) -> Agent` | Atualiza atributos informados em `kwargs`. Lança `EntityNotFoundError` se não existir. | - Rota web `POST /agents/{id}` |
| `delete(agent_id)` | `(agent_id: int) -> bool` | Remove o agente da base. Retorna `False` se não encontrado. | - Rota web `POST /agents/{id}/delete` |

---

## 3. `SqlProjectRepository`

Gerencia os projetos registrados e seus diretórios locais de trabalho (`Project`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(project_id)` | `(project_id: int) -> Project \| None` | Busca projeto por ID. | - `JobRunnerService`<br>- `PipelineOrchestrator`<br>- Rotas web: `jobs.py`, `projects.py` |
| `get_by_key(project_key)` | `(project_key: str) -> Project \| None` | Busca projeto por sua chave única externa. | - Consultas de validação no fluxo de projeto |
| `list_all(active_only=False)` | `(active_only: bool) -> list[Project]` | Lista todos os projetos ordenados por nome. | - `PipelineOrchestrator.run_all_active`<br>- CLI `pipeline run`<br>- Rotas web: `jobs.py`, `projects.py` |
| `create(project_key, name, ...)` | `(project_key, name, local_path, active=True) -> Project` | Registra novo projeto. | - Rota web `POST /projects/new` |
| `update(project_id, **kwargs)` | `(project_id: int, **kwargs: Any) -> Project` | Atualiza dados do projeto (ex.: `last_run_at`). Lança `EntityNotFoundError` se inexistente. | - `PipelineOrchestrator`<br>- Rota web `POST /projects/{id}` |
| `delete(project_id)` | `(project_id: int) -> bool` | Remove o projeto. Retorna `False` se não encontrado. | - Rota web `POST /projects/{id}/delete` |

---

## 4. `SqlFlowColumnRepository`

Gerencia o mapeamento de colunas do Kanban com os agentes (`FlowColumn`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(column_id)` | `(column_id: int) -> FlowColumn \| None` | Busca coluna por ID. | - `PipelineOrchestrator`<br>- Rotas web: `columns.py`, `jobs.py` |
| `get_by_identifier(identifier)` | `(identifier: str) -> FlowColumn \| None` | Busca coluna por identificador canônico (slug). | - `seed_database()` |
| `get_by_column_name(column_name)`| `(column_name: str) -> FlowColumn \| None` | Busca coluna pelo nome exato no quadro externo. | - Validações de transição |
| `list_all(active_only=False)` | `(active_only: bool) -> list[FlowColumn]` | Lista colunas ordenadas por `order_index`. | - `PipelineOrchestrator`<br>- `SyncService`<br>- Rotas web: `agents.py`, `columns.py`, `jobs.py`, `projects.py` |
| `create(identifier, column_name, ...)` | `(identifier, column_name, agent_id=None, next_column_name=None, order_index=0, active=True) -> FlowColumn` | Cria nova etapa no fluxo. | - `seed_database()`<br>- Rota web `POST /columns/new` |
| `update(column_id, **kwargs)` | `(column_id: int, **kwargs: Any) -> FlowColumn` | Atualiza parâmetros da coluna. Lança `EntityNotFoundError` se inexistente. | - Rota web `POST /columns/{id}` |
| `delete(column_id)` | `(column_id: int) -> bool` | Remove a coluna. Retorna `False` se não encontrada. | - Rota web `POST /columns/{id}/delete` |

---

## 5. `SqlJobRepository`

Gerencia os trabalhos de execução disparados para os cards (`Job`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(job_id)` | `(job_id: int) -> Job \| None` | Busca job por ID. | - `JobRunnerService.run_job`<br>- Rotas web: `jobs.py` |
| `list_all(project_id=None, card_id=None, state=None, limit=100)` | `(...) -> list[Job]` | Filtra e lista jobs por projeto, card ou estado (`pending`, `running`, etc.), ordenados pelos mais recentes. | - `JobRunnerService`<br>- `PipelineOrchestrator`<br>- CLI `pipeline jobs list`<br>- Rota web `GET /jobs` |
| `get_active_job_for_card(card_id, flow_column_id)` | `(card_id: int, flow_column_id: int) -> Job \| None` | Busca se já existe job em andamento ou pendente (`pending` ou `running`) para o card nesta coluna. Evita duplicação. | - `PipelineOrchestrator.run_for_project` |
| `create(project_id, card_id, ...)` | `(project_id, card_id, flow_column_id, agent_id, cli_provider_snapshot, model_id_snapshot, target_column_snapshot, state='pending', iteration=1) -> Job` | Cria novo job persistindo snapshots de agente, CLI e coluna alvo. | - `PipelineOrchestrator`<br>- Rota web `POST /jobs/new` |
| `update(job_id, **kwargs)` | `(job_id: int, **kwargs: Any) -> Job` | Atualiza estado (`running`, `succeeded`, `failed`), saídas, erros e timestamps. Lança `EntityNotFoundError` se inexistente. | - `JobRunnerService`<br>- `PipelineOrchestrator`<br>- Rota web: `jobs.py` |
| `delete(job_id)` | `(job_id: int) -> bool` | Remove o job. Retorna `False` se não encontrado. | - Rota web `POST /jobs/{id}/delete` |

---

## 6. `SqlCardRepository`

Gerencia o espelho local dos cards externos (`Card`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(card_id)` | `(card_id: int) -> Card \| None` | Busca card por ID. | - `JobRunnerService`<br>- `PipelineOrchestrator`<br>- Rota web `GET /jobs/card/{id}` |
| `get_by_remote_id(project_id, remote_id)` | `(project_id: int, remote_id: str) -> Card \| None` | Localiza o card pelo identificador original do quadro externo dentro do projeto. | - `SyncService.sync_cards` |
| `list_by_project(project_id, include_removed=False)` | `(project_id: int, include_removed: bool) -> list[Card]` | Lista cards do projeto ordenados por título, filtrando removidos se solicitado. | - `PipelineOrchestrator`<br>- `SyncService`<br>- CLI `pipeline run`<br>- Rotas web: `jobs.py`, `projects.py` |
| `create(project_id, remote_id, ...)` | `(project_id, remote_id, title, body, column_name, url=None, issue_number=None, content_hash=None) -> Card` | Cria o espelho local do card remoto. | - `SyncService.sync_cards` |
| `update(card_id, **kwargs)` | `(card_id: int, **kwargs: Any) -> Card` | Atualiza título, hash, coluna, contagem de retrabalho ou flag `removed`. Lança `EntityNotFoundError` se inexistente. | - `JobRunnerService`<br>- `SyncService` |

---

## 7. `SqlCardEventRepository`

Gerencia o histórico de transições e auditoria dos cards (`CardEvent`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `list_by_card(card_id)` | `(card_id: int) -> list[CardEvent]` | Retorna o histórico de eventos de um card específico em ordem cronológica reversa. | - Rota web `GET /jobs/card/{id}` |
| `list_recent(limit=50)` | `(limit: int) -> list[CardEvent]` | Lista os últimos eventos de movimentação no sistema. | - Painel e monitoramento |
| `create(card_id, event_type, ...)` | `(card_id, event_type, from_column=None, to_column=None, is_rework=False) -> CardEvent` | Registra evento de criação, alteração de coluna, alteração de conteúdo ou remoção. | - `SyncService.sync_cards`<br>- `JobRunnerService.run_job` |

---

## 8. `SqlCliModelRepository`

Gerencia o catálogo local de modelos de IA suportados por CLI (`CliModel`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `list_by_provider(cli_provider, available_only=True)` | `(cli_provider: str, available_only: bool) -> list[CliModel]` | Lista modelos de uma CLI específica (ex.: `"gemini"` ou `"claude"`), ordenados por rótulo. | - Rota web `GET /agents/models-options` (HTMX dinâmico no formulário) |
| `list_all(available_only=False)` | `(available_only: bool) -> list[CliModel]` | Lista todos os modelos catalogados no sistema. | - Diagnóstico e listagens gerais |
| `upsert_models(cli_provider, models)` | `(cli_provider: str, models: list[Any]) -> None` | Atualiza o catálogo do provedor: atualiza modelos existentes, insere novos e marca como `available=False` aqueles que não vieram mais na listagem atual. | - `ModelCatalogService.sync_models_for_provider`<br>- `ModelCatalogService.sync_all_installed_providers` |

---

## 9. `SqlPipelineRunRepository`

Gerencia o log das execuções de sincronização do pipeline (`PipelineRun`).

| Método | Assinatura | Função | Onde é Usado |
|---|---|---|---|
| `get_by_id(run_id)` | `(run_id: int) -> PipelineRun \| None` | Busca histórico de execução por ID. | - Rastreamento e logs detalhados |
| `list_recent(limit=50)` | `(limit: int) -> list[PipelineRun]` | Lista as últimas execuções ordenadas pela data de início descendente. | - Rota web `GET /jobs` (aba de histórico de execuções) |
| `create(trigger, project_provider_used, ...)` | `(trigger, project_provider_used, project_id=None, cli_provider_used=None) -> PipelineRun` | Abre registro de execução com status inicial `"ok"`. | - `PipelineOrchestrator.run_for_project` |
| `update(run_id, **kwargs)` | `(run_id: int, **kwargs: Any) -> PipelineRun` | Finaliza a execução atualizando métricas (`cards_synced`, `jobs_created`), `status`, `error` e `finished_at`. Lança `EntityNotFoundError` se inexistente. | - `PipelineOrchestrator.run_for_project` |
