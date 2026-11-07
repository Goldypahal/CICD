import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agents.orchestrator import GitFixOrchestrator
from .benchmark.runner import BenchmarkRunner
from .config import Config
from .detector import detect_project
from .git.repo_manager import GitRepoManager
from .git.watcher import GitWatcher
from .memory.error_db import ErrorDatabase

console = Console()


@click.group()
def cli():
    """GitFix-Agent: Production-Grade Autonomous AI Software Maintenance Engineer."""
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

    console.print(
        Panel.fit(
            f"[bold green]GitFix-Agent Initialized![/bold green]\n"
            f"Config file: [cyan]{config.config_path}[/cyan]\n"
            f"Git Hook Installed: {'[green]Yes[/green]' if hook_installed else '[yellow]No (not a git repo, or an existing post-commit hook was left untouched)[/yellow]'}",
            title="GitFix Setup",
        )
    )


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
    config = Config(str(repo_dir))
    table.add_row("Test Command", config.test_command_override or project_info.test_command or "None")
    table.add_row("Sandbox Image", project_info.sandbox_image or "None")
    table.add_row("Sandbox Setup", project_info.install_command or "None")
    table.add_row("Build Command", project_info.build_command or "None")
    table.add_row("Lint Command", project_info.lint_command or "None")
    table.add_row("Config Files Found", ", ".join(project_info.config_files) or "None")
    table.add_row("Is Git Repo", "Yes" if repo_mgr.is_git_repo() else "No")
    if repo_mgr.is_git_repo():
        table.add_row("Current Commit", repo_mgr.get_current_commit()[:7])
        table.add_row("Current Branch", repo_mgr.get_current_branch())

    console.print(table)


def _write_github_outputs(**values) -> None:
    """Expose results as GitHub Actions step outputs when running inside Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for key, value in values.items():
            f.write(f"{key}={'' if value is None else str(value).replace(chr(10), ' ')}\n")


@cli.command()
@click.option("--auto-commit", is_flag=True, help="Commit the fix on the current branch (no safety branch unless --auto-pr).")
@click.option("--auto-pr", is_flag=True, help="Commit on a safety branch, push it and open a GitHub Pull Request.")
@click.option("--sandbox/--no-sandbox", default=True, help="Run tests in an isolated Docker sandbox (default) or on the host.")
@click.option("--provider", type=str, help="Override LLM provider (nemotron, gemini, openai, ollama, mock).")
@click.option("--model", type=str, help="Override LLM model name.")
@click.option("--base-branch", type=str, default=None, help="Branch the PR should target (default: the branch you started on, else origin's default).")
def fix(auto_commit, auto_pr, sandbox, provider, model, base_branch):
    """Diagnose and automatically fix commit regressions in the project."""
    repo_dir = Path.cwd()
    config = Config(str(repo_dir))
    if provider:
        config._data["agent"]["provider"] = provider
        os.environ.pop("LLM_PROVIDER", None)  # explicit flag beats environment
    if model:
        config._data["agent"]["model"] = model
        os.environ.pop("LLM_MODEL", None)

    orchestrator = GitFixOrchestrator(repo_dir=repo_dir, config=config, use_sandbox=sandbox)
    res = orchestrator.run_repair_flow(auto_commit=auto_commit, auto_pr=auto_pr, base_branch=base_branch)
    _write_github_outputs(success=str(res.success).lower(), pr_url=res.pr_url or "", branch=res.branch_created or "")

    if res.success:
        console.print(f"[bold green]✨ {res.summary if res.retries_used == 0 else f'Repair completed successfully in {res.retries_used} attempt(s)!'}[/bold green]")
        if res.branch_created:
            console.print(f"Safety Branch created: [cyan]{res.branch_created}[/cyan]")
        if res.pr_url:
            console.print(f"GitHub Pull Request: [cyan]{res.pr_url}[/cyan]")
        if res.pr_error:
            console.print(f"[yellow]⚠️ {res.pr_error}[/yellow]")
            sys.exit(2)
    else:
        console.print(f"[bold red]❌ {res.summary}[/bold red]")
        sys.exit(1)


@cli.command()
def benchmark():
    """Run standardized multi-language AI coding evaluation benchmark suite."""
    repo_dir = Path.cwd()
    runner = BenchmarkRunner(repo_dir=repo_dir)
    runner.run_benchmark()


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
        orchestrator = GitFixOrchestrator(repo_dir=repo_dir, config=Config(str(repo_dir)))
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
