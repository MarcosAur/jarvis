# Exceptions

Definidas em [exceptions.py](../src/pipeline/domain/exceptions.py). Todas herdam de `DomainError`, então é possível capturar qualquer erro do domínio com um único `except DomainError`.

```
Exception
└── DomainError
    ├── ProviderNotInstalledError
    ├── ProviderExecutionError
    ├── BoardError
    ├── EntityNotFoundError
    ├── ValidationError
    └── ContractViolationError
```

| Exceção | Quando é lançada | Onde é usada |
|---|---|---|
| `DomainError` | Classe base, não é lançada diretamente. | — |
| `ProviderNotInstalledError` | O binário da CLI de IA não está instalado no sistema. | [base.py](../src/pipeline/adapters/cli_providers/base.py) |
| `ProviderExecutionError` | Falha ao executar a CLI: erro no comando, *timeout* ou falha do subprocesso. | [base.py](../src/pipeline/adapters/cli_providers/base.py) |
| `BoardError` | Falha ao interagir com o quadro externo: credenciais ausentes, chave de projeto inválida, erro HTTP/GraphQL, falha de rede, coluna ou projeto não encontrado. Também ocorre quando o provedor de projeto ativo não está registrado. | [github_projects.py](../src/pipeline/adapters/project_providers/github_projects.py), [jira_projects.py](../src/pipeline/adapters/project_providers/jira_projects.py), [trello_projects.py](../src/pipeline/adapters/project_providers/trello_projects.py), [pipeline_orchestrator.py](../src/pipeline/application/pipeline_orchestrator.py) |
| `EntityNotFoundError` | Uma entidade buscada por id não existe (agente, projeto, coluna, job, card ou execução). | [repositories.py](../src/pipeline/adapters/db/repositories.py), [pipeline_orchestrator.py](../src/pipeline/application/pipeline_orchestrator.py), [job_runner_service.py](../src/pipeline/application/job_runner_service.py) |
| `ContractViolationError` | Um provider não cumpre o contrato do port: atributo ausente ou vazio, método ausente ou assinatura diferente. Lançada em `Registry.register`. | [contract.py](../src/pipeline/domain/contract.py), [registry.py](../src/pipeline/domain/registry.py) |
| `ValidationError` | Reservada para falhas de validação de domínio. **Hoje não é lançada em nenhum ponto do código.** | — |

## Convenções

- Os adapters traduzem erros de bibliotecas (`httpx.RequestError`, falhas de `subprocess`) para exceções de domínio, usando `raise ... from e` para preservar a causa original.
- As mensagens de erro dos provedores de quadro estão em português; as dos repositórios, em inglês.
