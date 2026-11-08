from pipeline.adapters.db.engine import init_db
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork

DEFAULT_ARCHITECT_PROMPT = """# Agente Arquiteto de Software (Gemini)

Você é o Arquiteto de Software responsável por analisar a demanda do card e o repositório local.

## Suas Diretrizes:
1. Analise cuidadosamente a descrição do card e os arquivos existentes no projeto.
2. Siga os princípios SOLID, Clean Architecture e boas práticas de engenharia de software.
3. Produza um plano de arquitetura claro contendo:
   - Diagnóstico do estado atual
   - Especificação dos contratos e interfaces
   - Detalhamento das etapas de implementação
   - Critérios de aceitação e testes recomendados
4. Não altere o comportamento prévio desnecessariamente.
"""

DEFAULT_COLUMNS = [
    {"identifier": "todo", "column_name": "Todo", "needs_agent": False, "next_column_name": "To architect", "order_index": 1},
    {"identifier": "to_architect", "column_name": "To architect", "needs_agent": True, "next_column_name": "Architected", "order_index": 2},
    {"identifier": "architected", "column_name": "Architected", "needs_agent": False, "next_column_name": "In Progress", "order_index": 3},
    {"identifier": "in_progress", "column_name": "In Progress", "needs_agent": False, "next_column_name": "Homolog", "order_index": 4},
    {"identifier": "homolog", "column_name": "Homolog", "needs_agent": False, "next_column_name": "Done", "order_index": 5},
    {"identifier": "done", "column_name": "Done", "needs_agent": False, "next_column_name": None, "order_index": 6},
]


def seed_database(uow: SqlAlchemyUnitOfWork | None = None) -> None:
    init_db()
    work = uow or SqlAlchemyUnitOfWork()

    with work:
        # 1. Settings
        work.settings.get()

        # 2. Default Agent
        agent = work.agents.get_by_name("Arquiteto Gemini")
        if not agent:
            agent = work.agents.create(
                name="Arquiteto Gemini",
                cli_provider="agy",
                model_id="gemini-4-argon-medium",
                prompt_markdown=DEFAULT_ARCHITECT_PROMPT,
                active=True,
            )

        # 3. Flow Columns
        for col_data in DEFAULT_COLUMNS:
            existing = work.columns.get_by_identifier(col_data["identifier"])
            if not existing:
                work.columns.create(
                    identifier=col_data["identifier"],
                    column_name=col_data["column_name"],
                    agent_id=agent.id if col_data["needs_agent"] else None,
                    next_column_name=col_data["next_column_name"],
                    order_index=col_data["order_index"],
                    active=True,
                )

        work.commit()
