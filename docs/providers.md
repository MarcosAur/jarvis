# Providers

Um **provider** (adapter) é uma classe concreta que cumpre um [port](ports.md) e fala com algo externo: uma CLI de IA ou um quadro de projeto. Os providers ficam em [adapters](../src/pipeline/adapters/) e são guardados no [registry](registry.md).

## Providers de CLI de IA

Em [cli_providers](../src/pipeline/adapters/cli_providers/). Cumprem o port `CliModelProvider`.

| Classe | `provider_key` | `display_name` | `binary_name` |
|---|---|---|---|
| `AgyCliProvider` | `agy` | Antigravity CLI (Assinatura Gemini) | `agy` |
| `GeminiCliProvider` | `gemini` | Google Gemini CLI | `gemini` |
| `ClaudeCliProvider` | `claude` | Claude Code CLI | `claude` |
| `CodexCliProvider` | `codex` | OpenAI Codex CLI | `codex` |

### Classe base `BaseSubprocessCliProvider`

Todos herdam de [base.py](../src/pipeline/adapters/cli_providers/base.py), que traz o código comum:

- `is_installed()` usa `shutil.which(binary_name)`.
- `_ensure_installed()` lança `ProviderNotInstalledError` se o binário não existir.
- `_run_cmd()` executa o subprocesso com `timeout` (padrão `CLI_TIMEOUT_SECONDS`). Lança `ProviderExecutionError` se o código de saída for diferente de zero, se estourar o tempo ou se o subprocesso falhar.

Cada provider concreto só define os três atributos e implementa `list_models()` e `execute_prompt()`. A herança é reuso de código dentro dos adapters, e o registry não depende dela.

## Providers de quadro de projeto

Em [project_providers](../src/pipeline/adapters/project_providers/). Cumprem o port `ProjectProvider`.

| Classe | `provider_key` | `display_name` |
|---|---|---|
| `GitHubProjectProvider` | `github` | GitHub Projects (User v2) |
| `JiraProjectProvider` | `jira` | Atlassian Jira |
| `TrelloProjectProvider` | `trello` | Trello |

Todas herdam de `ProjectProvider` e implementam `settings_fields`, `test_connection`, `fetch_cards`, `move_card` e `add_comment`. Se faltar algum método, a classe não pode ser instanciada.

- Falam com as APIs via `httpx`.
- Traduzem os erros para `BoardError` (veja [exceptions.md](exceptions.md)).
- Recebem as credenciais pelo dicionário `settings`, que vem de `AppSettings.provider_settings`.

## Adicionar um novo provider

O contrato é imposto (veja [contracts.md](contracts.md)): um provider com método faltando ou assinatura diferente **não sobe**.

### Quadro de projeto (por exemplo, um quarto gerenciador)

1. Crie `adapters/project_providers/<nome>_projects.py` com uma classe que **herda de `ProjectProvider`**.
2. Defina `provider_key` e `display_name` (não podem ser vazios).
3. Implemente os cinco métodos, **com as mesmas assinaturas e anotações de tipo do port**.
4. Lance `BoardError` nas falhas.
5. Exporte em `adapters/project_providers/__init__.py` e registre em `register_defaults()`, em [bootstrap.py](../src/pipeline/bootstrap.py).
6. Rode `mypy` e `pytest`.

```python
class LinearProjectProvider(ProjectProvider):
    provider_key = "linear"
    display_name = "Linear"

    def settings_fields(self) -> list[SettingFieldSpec]: ...
    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo: ...
    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]: ...
    def move_card(self, project_key: str, remote_card_id: str, target_column_name: str, settings: dict[str, Any]) -> None: ...
    def add_comment(self, project_key: str, remote_card_id: str, markdown: str, settings: dict[str, Any]) -> None: ...
```

Erros que o impedem de subir:

| Erro cometido | Onde falha |
|---|---|
| Faltou um método | `mypy` e `TypeError` ao instanciar. |
| Nome ou tipo de parâmetro diferente do port | `ContractViolationError` em `register`. |
| Esqueceu a anotação de tipo | `ContractViolationError` em `register`. |
| `provider_key` ou `display_name` vazio | `ContractViolationError` em `register`. |

### CLI de IA

1. Crie uma classe em `adapters/cli_providers/` que herde de `BaseSubprocessCliProvider` (que já herda de `CliModelProvider`).
2. Defina `provider_key`, `display_name` e `binary_name`.
3. Implemente `list_models()` e `execute_prompt()` com as assinaturas do port.
4. Exporte em `adapters/cli_providers/__init__.py` e registre em `register_defaults()`.

> [!WARNING]
> Para um provider de quadro novo, as credenciais não aparecem sozinhas na tela de Configurações. A rota `POST /settings` tem os campos escritos no código, e `settings_fields()` ainda não é usado para gerar o formulário.
