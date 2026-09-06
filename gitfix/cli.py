import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import Config
from .detector import detect_project
from .git.repo_manager import GitRepoManager
from .git.watcher import GitWatcher
from .agents.orchestrator import GitFixOrchestrator
from .memory.error_db import ErrorDatabase

console = Console()

@click.group()
def cli():
    """GitFix-Agent: Autonomous repository-agnostic AI software maintenance agent."""
    pass

@cli.command()
def init():
    """Initialize GitFix-Agent configuration and git hooks in current project."""
    repo_dir = Path.cwd()
    config = Config(str(repo_dir))
    config.save()
    
    repo_mgr = GitRepoManager(repo_dir)
    hook_installed = False
    if repo_mgr.is_git_repo():
        watcher = GitWatcher(repo_mgr)
        hook_installed = watcher.install_post_commit_hook()

    console.print(Panel.fit(
        f"[bold green]GitFix-Agent Initialized![/bold green]\n"
        f"Config file: [cyan]{config.config_path}[/cyan]\n"
        f"Git Hook Installed: {'[green]Yes[/green]' if hook_installed else '[yellow]No (Not a git repo or permissions issue)[/yellow]'}",
        title="GitFix Setup"
    ))

@cli.command()
def analyze():
    """Inspect and auto-detect project language, framework, build, and test setup."""
    repo_dir = Path.cwd()
    project_info = detect_project(repo_dir)
    repo_mgr = GitRepoManager(repo_dir)
    
    table = Table(title="GitFix Project Inspection")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Language", project_info.language)
    table.add_row("Framework", project_info.framework or "None")
    table.add_row("Package Manager", project_info.package_manager or "None")
    table.add_row("Test Framework", project_info.test_framework or "None")
    table.add_row("Test Command", project_info.test_command or "None")
    table.add_row("Build Command", project_info.build_command or "None")
    table.add_row("Lint Command", project_info.lint_command or "None")
    table.add_row("Config Files Found", ", ".join(project_info.config_files) or "None")
    table.add_row("Is Git Repo", "Yes" if repo_mgr.is_git_repo() else "No")
    if repo_mgr.is_git_repo():
        table.add_row("Current Commit", repo_mgr.get_current_commit()[:7])
        table.add_row("Current Branch", repo_mgr.get_current_branch())

    console.print(table)

@cli.command()
@click.option("--auto-commit", is_flag=True, help="Automatically commit fix directly without safety branch.")
@click.option("--provider", type=str, help="Override LLM provider (gemini, openai, mock).")
@click.option("--model", type=str, help="Override LLM model name.")
def fix(auto_commit, provider, model):
    """Diagnose and automatically fix commit regressions in the project."""
    repo_dir = Path.cwd()
    config = Config(str(repo_dir))
    if provider:
        config._data["agent"]["provider"] = provider
    if model:
        config._data["agent"]["model"] = model

    orchestrator = GitFixOrchestrator(repo_dir=repo_dir, config=config)
    res = orchestrator.run_repair_flow(auto_commit=auto_commit)

    if res.success:
        console.print(f"[bold green]✨ Repair completed successfully in {res.retries_used} attempt(s)![/bold green]")
        if res.branch_created:
            console.print(f"Safety Branch created: [cyan]{res.branch_created}[/cyan]")
    else:
        console.print(f"[bold red]❌ Repair failed after {res.retries_used} attempt(s).[/bold red]")

@cli.command()
def watch():
    """Continuously monitor git commits and repair failures automatically."""
    repo_dir = Path.cwd()
    repo_mgr = GitRepoManager(repo_dir)
    if not repo_mgr.is_git_repo():
        console.print("[bold red]Error: Current directory is not a Git repository.[/bold red]")
        return

    def on_new_commit(commit_hash: str):
        console.print(f"[bold yellow]Triggering automated fix workflow for {commit_hash[:7]}...[/bold yellow]")
        orchestrator = GitFixOrchestrator(repo_dir=repo_dir)
        orchestrator.run_repair_flow()

    watcher = GitWatcher(repo_mgr)
    watcher.watch(on_new_commit)

@cli.command()
def history():
    """Display historical error signatures and successful AI fixes."""
    repo_dir = Path.cwd()
    db = ErrorDatabase(repo_dir / ".gitfix" / "history.json")
    records = db.get_all_records()

    if not records:
        console.print("[yellow]No historical fix records found.[/yellow]")
        return

    table = Table(title="GitFix Historical Repairs (RAG Memory)")
    table.add_column("Commit", style="cyan")
    table.add_column("Error Type", style="red")
    table.add_column("Summary / Solution", style="green")
    table.add_column("Modified Files", style="magenta")

    for rec in records:
        table.add_row(
            rec.get("commit_hash", "")[:7],
            rec.get("error_type", "Error"),
            rec.get("summary", ""),
            ", ".join(rec.get("modified_files", [])),
        )

    console.print(table)

if __name__ == "__main__":
    cli()
