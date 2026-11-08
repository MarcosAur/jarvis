import os
from pathlib import Path
import pytest
from pipeline.adapters.db import engine as db_engine
from pipeline.adapters.db.engine import init_db, reset_engine
from pipeline.adapters.db.seed import seed_database
from pipeline.config import config

TEST_DB_PATH = Path("data/test_pipeline.db")
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH.resolve()}"


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Garante que todos os testes rodem em uma conexão e banco SQLite separados (data/test_pipeline.db),
    sem nunca interferir ou poluir o banco de dados principal (data/pipeline.db)."""
    # 1. Limpa qualquer arquivo remanescente de testes anteriores
    for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    # 2. Configura a URL de banco para apontar para o banco de teste
    original_db_url = config.DATABASE_URL
    config.DATABASE_URL = TEST_DB_URL
    reset_engine()

    # 3. Cria as tabelas e popula o seed no banco de teste
    test_engine = db_engine.get_engine(TEST_DB_URL)
    init_db(test_engine)
    seed_database()

    yield

    # 4. Teardown: fecha conexões e remove o banco de teste
    reset_engine()
    config.DATABASE_URL = original_db_url
    for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
