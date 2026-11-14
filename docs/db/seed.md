# Seed de Inicialização do Banco

Implementado em [seed.py](../../src/pipeline/adapters/db/seed.py). É responsável pelo povoamento inicial (*seed*) de dados operacionais obrigatórios para o pipeline entrar em execução imediatamente após a instalação.

## Visão Geral

A função principal `seed_database(uow=None)` é **idempotente**: pode ser executada repetidas vezes sem duplicar registros ou sobrescrever dados customizados já existentes.

## O que é Inicializado

### 1. Inicialização do Esquema
Invoca `init_db()` para assegurar que todas as tabelas mapeadas no `SQLModel.metadata` estejam criadas no banco de dados.

### 2. Configurações Globais (`AppSettings`)
Invoca `uow.settings.get()`. Se não houver configuração com `id=1`, inicializa os valores padrão:
- `default_cli_provider`: `"agy"`
- `active_project_provider`: `"github"`
- `provider_settings`: `{}`

### 3. Agente Padrão: "Arquiteto Gemini"
Se o agente não existir por nome, cadastra o agente inicial do fluxo:
- **Nome**: `"Arquiteto Gemini"`
- **Provedor de CLI**: `"agy"`
- **Modelo de IA**: `"gemini-4-argon-medium"`
- **Diretrizes operacionais (`prompt_markdown`)**: Contém instruções arquiteturais focadas em Clean Architecture, SOLID e geração de diagnósticos e contratos.

### 4. Colunas de Fluxo Padrão (`DEFAULT_COLUMNS`)
Registra as 6 colunas canônicas do Kanban de desenvolvimento caso seus identificadores ainda não existam:

| Ordem | Identificador | Nome no Quadro | Assistido por Agente? | Coluna Alvo Seguinte |
|---|---|---|---|---|
| 1 | `todo` | `Todo` | Não | `To architect` |
| 2 | `to_architect` | `To architect` | **Sim** (vinculado ao `Arquiteto Gemini`) | `Architected` |
| 3 | `architected` | `Architected` | Não | `In Progress` |
| 4 | `in_progress` | `In Progress` | Não | `Homolog` |
| 5 | `homolog` | `Homolog` | Não | `Done` |
| 6 | `done` | `Done` | Não | *Nenhuma* |

## Funções e Uso

| Função / Constante | Descrição | Onde é Usado |
|---|---|---|
| `seed_database(uow=None)` | Garante a criação do schema e insere os registros padrão via Unit of Work. | - Inicialização da aplicação web ([web/app.py](../../src/pipeline/web/app.py)) no evento de startup (*lifespan*)<br>- Comando CLI `pipeline db init` ([cli.py](../../src/pipeline/cli.py))<br>- Fixtures de testes em [conftest.py](../../tests/conftest.py), [test_web_cruds.py](../../tests/test_web_cruds.py) e [test_pipeline_orchestrator.py](../../tests/test_pipeline_orchestrator.py) |
| `DEFAULT_ARCHITECT_PROMPT` | String markdown contendo o prompt inicial de sistema do agente de arquitetura. | Dentro de `seed_database()` na criação do agente inicial |
| `DEFAULT_COLUMNS` | Lista de dicionários descrevendo as colunas e transições iniciais do pipeline. | Dentro de `seed_database()` no loop de criação de `FlowColumn` |

## Como Executar Manualmente

Pela linha de comando do sistema:
```bash
pipeline db init
```

Ou via Python:
```python
from pipeline.adapters.db.seed import seed_database

seed_database()
```
