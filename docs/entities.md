# Entidades

## Entidades persistidas (banco de dados)

Definidas em [orm_models.py](../src/pipeline/adapters/db/orm_models.py) (SQLModel).

| Entidade | Tabela | Função |
|---|---|---|
| `AppSettings` | `app_settings` | Configuração global (registro único, `id=1`): CLI de IA padrão (`default_cli_provider`), provedor de quadro ativo (`active_project_provider`) e credenciais/ajustes do provedor (`provider_settings`, JSON). |
| `CliModel` | `cli_models` | Catálogo de modelos de IA disponíveis por CLI (`cli_provider`, `model_id`, `label`, `family`, `available`). Preenchido por `pipeline models sync`. |
| `Agent` | `agents` | Agente de IA: nome único, CLI, modelo e `prompt_markdown` (prompt de sistema). Define *quem* executa e *com qual instrução*. |
| `Project` | `projects` | Projeto monitorado: `project_key` (identificador no provedor do quadro), `name`, `local_path` (diretório onde a CLI roda) e `last_run_at`. |
| `FlowColumn` | `flow_columns` | Regra de fluxo: liga uma coluna do quadro (`column_name`) a um `Agent`, e define a coluna de destino (`next_column_name`) e a ordem (`order_index`). |
| `Card` | `cards` | Cópia local de um card do quadro (título, corpo, coluna, URL, nº da issue, `content_hash`, `rework_count`, `removed`). Base para detectar mudanças. |
| `CardEvent` | `card_events` | Histórico de mudanças de um card: criado, mudou de coluna, conteúdo alterado ou removido (`from_column`/`to_column`, `is_rework`). |
| `Job` | `jobs` | Unidade de trabalho: um card numa coluna de fluxo a ser processado por um agente. Guarda *snapshots* de CLI/modelo/coluna destino, `iteration`, `state`, resumo da saída, erro e tempos. |
| `PipelineRun` | `pipeline_runs` | Registro de cada execução do pipeline (sincronização): gatilho, provedores usados, cards sincronizados, jobs criados, status e erro. |

**Relacionamentos:** `FlowColumn → Agent`; `Card → Project`; `CardEvent → Card`; `Job → Project, Card, FlowColumn, Agent`; `PipelineRun → Project`.

## Entidades de domínio (objetos de valor)

Definidas em [entities.py](../src/pipeline/domain/entities.py), imutáveis e independentes de framework.

| Entidade | Função |
|---|---|
| `JobState` (enum) | Estados de um job: `pending`, `running`, `succeeded`, `failed`, `cancelled`. |
| `CardEventType` (enum) | Tipos de evento de card: `created`, `column_changed`, `content_changed`, `removed`. |
| `RunTrigger` (enum) | Origem de uma execução: `web_project`, `web_all`, `cli`. |
| `RunStatus` (enum) | Resultado de uma execução: `ok`, `partial`, `error`. |
| `ModelOption` | Modelo de IA retornado por uma CLI (`id`, `label`, `family`, `cli_provider`). |
| `CliPromptRequest` | Requisição enviada à CLI: modelo, prompt de sistema (do agente), prompt da tarefa (do card) e diretório de trabalho. |
| `CliPromptResult` | Resposta da CLI: sucesso, texto de saída, tokens de entrada/saída, metadados e mensagem de erro. |
| `SettingFieldSpec` | Descreve um campo de configuração exigido por um provedor (tipo, obrigatório, segredo, opções), usado para montar o formulário de Configurações. |
| `RemoteCard` | Card como vem do provedor externo, antes de ser sincronizado com `Card`. |
| `BoardInfo` | Resumo de um quadro (título, total de cards, colunas) retornado no teste de conexão. |
