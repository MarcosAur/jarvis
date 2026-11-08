import sys
import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from pipeline.adapters.db.seed import seed_database
from pipeline.application.model_catalog_service import ModelCatalogService
from pipeline.application.pipeline_orchestrator import PipelineOrchestrator
from pipeline.adapters.db.uow import SqlAlchemyUnitOfWork
from pipeline.bootstrap import cli_registry, project_registry
from pipeline.config import config

app = typer.Typer(
    name="pipeline",
    help="Pipeline de Desenvolvimento Automático com IA — Arquitetura Open Source & SOLID",
    add_completion=False,
)
db_app = typer.Typer(name="db", help="Comandos de gerenciamento do banco de dados")
models_app = typer.Typer(name="models", help="Comandos de catálogo de modelos de IA")

app.add_typer(db_app)
app.add_typer(models_app)
console = Console()


@db_app.command("init")
def db_init():
    """Inicializa as tabelas do SQLite e popula o Seed inicial (Settings, Agente e Colunas)."""
    console.print("[bold cyan]Inicializando banco de dados e seed...[/bold cyan]")
    seed_database()
    console.print("[bold green]✔ Banco de dados pronto e populado com sucesso![/bold green]")


@models_app.command("sync")
def models_sync():
    """Sincroniza modelos disponíveis de todas as CLIs instaladas."""
    console.print("[bold cyan]Sincronizando modelos das CLIs instaladas...[/bold cyan]")
    catalog = ModelCatalogService(SqlAlchemyUnitOfWork)
    results = catalog.sync_all_installed_providers()

    table = Table(title="Modelos por Provedor CLI")
    table.add_column("Provedor", style="bold yellow")
    table.add_column("Modelos Encontrados", justify="right", style="green")

    for k, v in results.items():
        table.add_row(k, str(v))

    console.print(table)


@app.command("run")
def run_pipeline(
    project_id: int | None = typer.Option(None, "--project", "-p", help="ID do projeto para rodar especificamente"),
):
    """Executa a leitura dos quadros, sincroniza cards e enfileira jobs para colunas com agentes."""
    orchestrator = PipelineOrchestrator(SqlAlchemyUnitOfWork)

    if project_id is not None:
        console.print(f"[bold cyan]Rodando pipeline para o projeto #{project_id}...[/bold cyan]")
        run = orchestrator.run_for_project(project_id, trigger="cli")
        console.print(f"[bold green]Concluído![/bold green] Status: {run.status} | Cards: {run.cards_synced} | Jobs: {run.jobs_created}")
        if run.error:
            console.print(f"[bold red]Erro:[/bold red] {run.error}")
    else:
        console.print("[bold cyan]Rodando pipeline para todos os projetos ativos...[/bold cyan]")
        runs = orchestrator.run_all_active(trigger="cli")
        console.print(f"[bold green]Concluído![/bold green] Executado para {len(runs)} projeto(s).")
        for r in runs:
            console.print(f" - Projeto #{r.project_id}: status={r.status}, cards={r.cards_synced}, jobs={r.jobs_created}")


@app.command("web")
def run_web(
    host: str = typer.Option(config.HOST, "--host", "-h", help="Host do servidor"),
    port: int = typer.Option(config.PORT, "--port", "-p", help="Porta do servidor"),
    reload: bool = typer.Option(config.DEBUG, "--reload", help="Habilitar auto-reload"),
):
    """Inicia o servidor web da aplicação (FastAPI + HTMX)."""
    console.print(f"[bold green]Iniciando AI Pipeline Web em http://{host}:{port}[/bold green]")
    uvicorn.run("pipeline.web.app:app", host=host, port=port, reload=reload)


def main():
    app()


if __name__ == "__main__":
    main()
