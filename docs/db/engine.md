# Engine e Conexão com o Banco de Dados

Implementado em [engine.py](../../src/pipeline/adapters/db/engine.py). Gerencia a conexão com o banco de dados via **SQLAlchemy** e **SQLModel**, aplicando configurações de desempenho, concorrência e integridade referencial.

## Visão Geral

O módulo gerencia a instância singleton do `Engine` do SQLAlchemy, assegura a existência dos diretórios locais (quando em SQLite) e configura flags essenciais para execução assíncrona/multi-thread (como no FastAPI).

### Configurações SQLite

Quando a URL do banco é SQLite (`sqlite:///...`), o motor aplica via evento `connect`:
1. `PRAGMA journal_mode=WAL`: ativa o modo **Write-Ahead Logging**, permitindo leituras simultâneas sem bloquear escritas.
2. `PRAGMA foreign_keys=ON`: ativa a checagem obrigatória de chaves estrangeiras no SQLite (que por padrão vem desativada).
3. `connect_args={"check_same_thread": False}`: permite o compartilhamento de conexões entre threads disparadas pelo servidor web FastAPI.

## Funções do Módulo

| Função | Parâmetros | Descrição | Onde é Usado |
|---|---|---|---|
| `get_engine(db_url=None)` | `db_url: str \| None` | Retorna o `Engine` singleton configurado. Se `db_url` for omitida, utiliza `config.DATABASE_URL` (padrão `sqlite:///data/pipeline.db`). Garante que a pasta `data/` exista antes de conectar. | - `init_db()`<br>- [uow.py](../../src/pipeline/adapters/db/uow.py) (fábrica padrão de `Session`)<br>- [conftest.py](../../tests/conftest.py) (criação da base de teste) |
| `init_db(engine=None)` | `engine: Engine \| None` | Executa `SQLModel.metadata.create_all(eng)` para criar todas as tabelas no banco caso ainda não existam. | - [seed.py](../../src/pipeline/adapters/db/seed.py) (na inicialização do banco)<br>- [conftest.py](../../tests/conftest.py) e [test_pipeline_orchestrator.py](../../tests/test_pipeline_orchestrator.py)<br>- CLI `pipeline db init` (via `seed_database`) |
| `reset_engine()` | Nenhum | Descarta (`dispose()`) a engine ativa e reseta a variável global `_engine` para `None`. | - [conftest.py](../../tests/conftest.py) (limpeza de conexões e arquivos entre baterias de testes) |

## Exemplo de Uso

```python
from pipeline.adapters.db.engine import get_engine, init_db

# Inicializar schema no banco padrão
init_db()

# Obter engine para uso direto ou em testes
engine = get_engine("sqlite:///:memory:")
init_db(engine)
```
