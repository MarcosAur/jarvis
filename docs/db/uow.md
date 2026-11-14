# Unit of Work (UoW)

Implementado em [uow.py](../../src/pipeline/adapters/db/uow.py). A classe `SqlAlchemyUnitOfWork` implementa o port de domínio [UnitOfWork](../../src/pipeline/domain/ports/uow.py), agrupando operações sobre múltiplos repositórios em uma única transação atômica.

## Padrão Unit of Work

O Unit of Work evita que serviços de aplicação ou rotas HTTP manipulem conexões e transações de banco de dados diretamente. Ele garante que:
1. Uma única `Session` do SQLAlchemy seja compartilhada entre todos os repositórios durante a requisição ou caso de uso.
2. Em caso de erro não tratado dentro do bloco `with uow:`, o método `__exit__` execute automaticamente o `rollback()`.
3. A sessão seja sempre fechada ao final do bloco (`session.close()`).

```mermaid
flowchart TD
    SVC["Caso de Uso / Rota Web"] -->|with uow:| UOW[SqlAlchemyUnitOfWork]
    UOW -->|instancia| SESS[Session]
    UOW -->|disponibiliza| R1[uow.agents]
    UOW -->|disponibiliza| R2[uow.cards]
    UOW -->|disponibiliza| R3[uow.jobs]
    UOW -->|disponibiliza| RN[...]
    R1 -. compartilha .-> SESS
    R2 -. compartilha .-> SESS
    R3 -. compartilha .-> SESS
    SVC -->|uow.commit()| SESS
    UOW -->|__exit__ rollback se exceção| SESS
    UOW -->|__exit__ close| SESS
```

## Estrutura e Repositórios Disponibilizados

Quando o bloco de contexto é aberto (`__enter__`), os seguintes repositórios ficam disponíveis no objeto:

| Atributo | Tipo do Repositório | Entidade Gerenciada |
|---|---|---|
| `uow.settings` | `SqlSettingsRepository` | `AppSettings` |
| `uow.agents` | `SqlAgentRepository` | `Agent` |
| `uow.projects` | `SqlProjectRepository` | `Project` |
| `uow.columns` | `SqlFlowColumnRepository` | `FlowColumn` |
| `uow.jobs` | `SqlJobRepository` | `Job` |
| `uow.cards` | `SqlCardRepository` | `Card` |
| `uow.events` | `SqlCardEventRepository` | `CardEvent` |
| `uow.models` | `SqlCliModelRepository` | `CliModel` |
| `uow.runs` | `SqlPipelineRunRepository` | `PipelineRun` |

## Ciclo de Vida e Métodos

| Método | Função | Onde é Usado |
|---|---|---|
| `__init__(session_factory=None)` | Recebe uma fábrica de sessões opcional. Se omitida, cria `Session(get_engine(), expire_on_commit=False)`. O parâmetro `expire_on_commit=False` permite que entidades continuem acessíveis após `commit()`. | - `dependencies.py` (FastAPI)<br>- `cli.py` (Typer)<br>- Testes unitários / de integração (injeção de sessão em memória) |
| `__enter__()` | Abre a sessão, inicializa os 9 repositórios vinculados a ela e retorna a própria instância do `UnitOfWork`. | Ao iniciar blocos `with uow:` em qualquer serviço ou rota |
| `__exit__(exc_type, exc_val, exc_tb)` | Se ocorreu exceção (`exc_type is not None`), aciona `self.rollback()`. Fecha a sessão via `self.session.close()`. | Ao sair do bloco `with uow:` |
| `commit()` | Confirma as alterações pendentes no banco de dados (`self.session.commit()`). | Chamado explicitamente após operações de escrita bem-sucedidas |
| `rollback()` | Descarta alterações não commitadas na sessão (`self.session.rollback()`). | Chamado automaticamente em falhas ou manualmente quando necessário |

## Injeção de Dependência

### Na Camada Web (FastAPI)
Em [dependencies.py](../../src/pipeline/web/dependencies.py) ou `adapters/inbound/web/dependencies.py`:
```python
def get_uow() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork()

@router.get("/agents")
def list_agents(uow: SqlAlchemyUnitOfWork = Depends(get_uow)):
    with uow:
        return uow.agents.list_all()
```

### Nos Serviços de Aplicação
Os serviços recebem uma fábrica de UoW (`uow_factory: Callable[[], UnitOfWork]`):
```python
class JobRunnerService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    def run_job(self, job_id: int):
        with self.uow_factory() as uow:
            job = uow.jobs.get_by_id(job_id)
            uow.jobs.update(job.id, state="running")
            uow.commit()
```

### Em Testes
Permite injetar uma `Session` conectada a um banco SQLite em memória:
```python
mem_engine = create_engine("sqlite:///:memory:")
init_db(mem_engine)

uow_factory = lambda: SqlAlchemyUnitOfWork(
    lambda: Session(mem_engine, expire_on_commit=False)
)

with uow_factory() as uow:
    uow.projects.create(...)
    uow.commit()
```
