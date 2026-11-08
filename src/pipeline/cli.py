import sys
import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from pipeline.adapters.db.seed import seed_database
from pipeline.application.job_runner_service import JobRunnerService
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
jobs_app = typer.Typer(name="jobs", help="Comandos de gerenciamento e execução da fila de jobs")

app.add_typer(db_app)
app.add_typer(models_app)
app.add_typer(jobs_app)
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


@jobs_app.command("list")
def list_jobs_cmd(
    project_id: int | None = typer.Option(None, "--project", "-p", help="Filtrar por ID do projeto"),
    state: str | None = typer.Option(None, "--state", "-s", help="Filtrar por estado (pending, running, succeeded, failed, cancelled)"),
):
    """Lista os jobs cadastrados na fila com filtros opcionais."""
    with SqlAlchemyUnitOfWork() as uow:
        raw_jobs = uow.jobs.list_all(project_id=project_id, state=state)
        projects = {p.id: p.name for p in uow.projects.list_all()}
        cards = {c.id: c.title for c in uow.cards.list_by_project(project_id) if project_id} if project_id else {}

        table = Table(title="Fila de Jobs & Execuções")
        table.add_column("ID", style="bold cyan", justify="right")
        table.add_column("Projeto", style="yellow")
        table.add_column("Card ID", justify="right")
        table.add_column("Coluna Snapshot", style="magenta")
        table.add_column("Provedor/Modelo", style="blue")
        table.add_column("Estado", style="bold")

        for j in raw_jobs:
            color = {
                "pending": "yellow",
                "running": "blue",
                "succeeded": "green",
                "failed": "red",
                "cancelled": "dim",
            }.get(j.state, "white")

            table.add_row(
                str(j.id),
                projects.get(j.project_id, str(j.project_id)),
                str(j.card_id),
                j.target_column_snapshot or "—",
                f"{j.cli_provider_snapshot or '—'}/{j.model_id_snapshot or '—'}",
                f"[{color}]{j.state}[/{color}]",
            )

        console.print(table)


@jobs_app.command("run")
def run_jobs_cmd(
    job_id: int | None = typer.Option(None, "--job-id", "-j", help="ID de um job específico a ser executado"),
    project_id: int | None = typer.Option(None, "--project", "-p", help="ID do projeto para filtrar jobs pendentes"),
    live: bool = typer.Option(True, "--live/--dry-run", help="Executar com a CLI de IA real (padrão) ou simulação (--dry-run)"),
):
    """Executa jobs pendentes da fila (ou um job específico). Por padrão roda em modo LIVE com a IA."""
    runner = JobRunnerService(SqlAlchemyUnitOfWork)
    dry_run = not live
    mode_label = "[bold green]LIVE (CLI de IA Real)[/bold green]" if live else "[bold yellow]DRY-RUN (Simulação)[/bold yellow]"
    console.print(f"Iniciando execução no modo {mode_label}...")

    if job_id is not None:
        res = runner.run_job(job_id, dry_run=dry_run)
        if res.get("success"):
            console.print(f"[bold green]✔ Job #{job_id} executado com sucesso![/bold green]")
            if res.get("summary"):
                console.print(f"  Saída: {res.get('summary')}")
        else:
            console.print(f"[bold red]✘ Falha no Job #{job_id}:[/bold red] {res.get('error')}")
    else:
        results = runner.run_all_pending(project_id=project_id, dry_run=dry_run)
        console.print(f"[bold green]✔ Processados {len(results)} job(s) pendente(s).[/bold green]")
        for r in results:
            status = "[green]OK[/green]" if r.get("success") else "[red]FALHA[/red]"
            console.print(f" - Job #{r.get('job_id')}: {status}")


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
