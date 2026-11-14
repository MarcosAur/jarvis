# Modelos ORM (Tabelas do Banco de Dados)

Definido em [orm_models.py](../../src/pipeline/adapters/db/orm_models.py). Contém as classes que mapeiam as tabelas relacionais do banco via **SQLModel** (que une SQLAlchemy e Pydantic).

> Para a visão dos objetos de valor de domínio imutáveis, consulte também [entities.md](../entities.md).

## Diagrama Entidade-Relacionamento (ER)

```mermaid
erDiagram
    PROJECT ||--o{ CARD : "possui"
    PROJECT ||--o{ JOB : "executa"
    PROJECT ||--o{ PIPELINE_RUN : "registra"
    CARD ||--o{ CARD_EVENT : "gera histórico"
    CARD ||--o{ JOB : "alvo do trabalho"
    AGENT ||--o{ FLOW_COLUMN : "atribuído a"
    AGENT ||--o{ JOB : "executa trabalho"
    FLOW_COLUMN ||--o{ JOB : "etapa do trabalho"

    APP_SETTINGS {
        int id PK
        string default_cli_provider
        string active_project_provider
        json provider_settings
        datetime updated_at
    }

    CLI_MODEL {
        int id PK
        string cli_provider
        string model_id
        string label
        string family
        bool available
        datetime last_synced_at
    }

    AGENT {
        int id PK
        string name UK
        string cli_provider
        string model_id
        string prompt_markdown
        bool active
        datetime created_at
        datetime updated_at
    }

    PROJECT {
        int id PK
        string project_key UK
        string name
        string local_path
        bool active
        datetime last_run_at
        datetime created_at
        datetime updated_at
    }

    FLOW_COLUMN {
        int id PK
        string identifier UK
        string column_name UK
        int agent_id FK
        string next_column_name
        int order_index
        bool active
        datetime created_at
        datetime updated_at
    }

    CARD {
        int id PK
        int project_id FK
        string remote_id
        string title
        string body
        string column_name
        string url
        int issue_number
        string content_hash
        int rework_count
        bool removed
        datetime first_seen_at
        datetime last_seen_at
    }

    CARD_EVENT {
        int id PK
        int card_id FK
        string event_type
        string from_column
        string to_column
        bool is_rework
        datetime created_at
    }

    JOB {
        int id PK
        int project_id FK
        int card_id FK
        int flow_column_id FK
        int agent_id FK
        string cli_provider_snapshot
        string model_id_snapshot
        string target_column_snapshot
        int iteration
        string state
        string output_summary
        string error
        datetime created_at
        datetime started_at
        datetime finished_at
    }

    PIPELINE_RUN {
        int id PK
        int project_id FK
        string trigger
        string project_provider_used
        string cli_provider_used
        int cards_synced
        int jobs_created
        string status
        string error
        datetime started_at
        datetime finished_at
    }
```

## Detalhamento das Tabelas

### 1. `AppSettings` (`app_settings`)
Registro único (`id=1`) que armazena a configuração operacional global do sistema.
- `default_cli_provider`: Provedor padrão de CLI de IA (`agy`, `gemini`, `claude`, `codex`).
- `active_project_provider`: Provedor ativo de quadro (`github`, `jira`, `trello`).
- `provider_settings`: Coluna `JSON` que guarda tokens, credenciais e parâmetros específicos de cada provedor externo de projeto.

### 2. `CliModel` (`cli_models`)
Catálogo sincronizado dos modelos de IA oferecidos por cada CLI instalada.
- Índices em `cli_provider` e `model_id`.
- `available`: Flag booleana que indica se o modelo continua ativo no provedor após o último sync.

### 3. `Agent` (`agents`)
Configuração de um agente autônomo de IA.
- `name`: Nome único do agente (indexado).
- `cli_provider` e `model_id`: Identificação da CLI e do modelo específico utilizado.
- `prompt_markdown`: Prompt de sistema / diretrizes operacionais do agente.

### 4. `Project` (`projects`)
Representa um projeto/repositório gerenciado pelo pipeline.
- `project_key`: Identificador único no provedor externo (ex: `owner/12` no GitHub ou chave no Jira/Trello).
- `local_path`: Caminho no sistema de arquivos local onde a CLI do agente executará as alterações.
- `last_run_at`: Timestamp da última sincronização realizada pelo orquestrador.

### 5. `FlowColumn` (`flow_columns`)
Mapeia o fluxo de trabalho (Kanban) e associa colunas a agentes de IA.
- `column_name`: Nome exato da coluna no quadro externo.
- `agent_id`: FK opcional para `agents.id`. Se preenchido, cards nesta coluna disparam jobs com este agente.
- `next_column_name`: Coluna de destino sugerida para avanço automático pós-processamento.
- `order_index`: Posição ordinal para ordenação das colunas no fluxo.

### 6. `Card` (`cards`)
Espelho persistido de um card/issue externo do quadro.
- `project_id`: FK para `projects.id`.
- `remote_id`: Identificador original no provedor externo.
- `content_hash`: Hash SHA-256 do título + corpo para detectar alterações no conteúdo do card.
- `rework_count`: Contador incrementado quando um card retorna para uma coluna anterior no fluxo.
- `removed`: Flag que indica se o card foi deletado ou movido para fora do escopo no quadro remoto.

### 7. `CardEvent` (`card_events`)
Trilha de auditoria e métricas de movimentação dos cards.
- `event_type`: Tipo de ocorrência (`created`, `column_changed`, `content_changed`, `removed`).
- `from_column` e `to_column`: Transição de colunas.
- `is_rework`: Indica se o evento representou retrabalho.

### 8. `Job` (`jobs`)
Unidade de trabalho atômica gerada quando um card entra em uma coluna assistida por agente.
- `state`: Estado da execução (`pending`, `running`, `succeeded`, `failed`, `cancelled`).
- Snapshots (`cli_provider_snapshot`, `model_id_snapshot`, `target_column_snapshot`): Preservam a configuração do momento da criação do job, prevenindo inconsistências caso o agente ou coluna sejam editados depois.
- `output_summary` e `error`: Resumo do resultado retornado pela CLI ou stack trace em caso de falha.

### 9. `PipelineRun` (`pipeline_runs`)
Histórico de execuções do ciclo do orquestrador.
- `trigger`: Gatilho disparador (`web_project`, `web_all`, `cli`).
- `cards_synced` e `jobs_created`: Métricas quantitativas da execução.
- `status`: Resultado global (`ok`, `partial`, `error`).
