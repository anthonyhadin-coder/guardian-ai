from __future__ import annotations
import argparse
import sys
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from guardian_ai.agent import GuardianAgent
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.models import ExecutionTraceStep, StepStatus
from guardian_ai.core.reporter import ReportGenerator
from guardian_ai.providers.factory import get_llm_provider

console = Console()

def handle_run(args):
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        console.print(f"[bold red]Error:[/bold red] Repository path '{repo_path}' does not exist.")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]Guardian AI — Autonomous SWE Agent[/bold cyan]\n"
        f"[dim]Repository:[/dim] {repo_path}\n"
        f"[dim]Task:[/dim] {args.task}\n"
        f"[dim]Provider:[/dim] {args.provider or 'Auto-Detected'}",
        title="[bold yellow]STARTING AUTONOMOUS AGENT RUN[/bold yellow]",
        border_style="cyan"
    ))

    provider = get_llm_provider(args.provider)
    console.print(f"[dim]Active Intelligence Provider: {provider.get_provider_name()}[/dim]\n")

    def on_step(step: ExecutionTraceStep):
        status_color = {
            StepStatus.RUNNING: "cyan",
            StepStatus.SUCCESS: "green",
            StepStatus.FAILED: "red",
            StepStatus.SKIPPED: "yellow"
        }.get(step.status, "white")
        icon = {
            StepStatus.RUNNING: "⏳",
            StepStatus.SUCCESS: "✓",
            StepStatus.FAILED: "✗",
            StepStatus.SKIPPED: "↷"
        }.get(step.status, "•")
        
        console.print(f"[{status_color}]{icon} [{step.step_id}] {step.name}[/{status_color}]")
        if step.details:
            console.print(f"  [dim]{step.details}[/dim]")

    agent = GuardianAgent(
        repo_path=repo_path,
        provider=provider,
        max_repair_iterations=args.max_iterations,
        event_callback=on_step
    )

    try:
        report = agent.run(args.task)
        console.print("\n")
        console.print(ReportGenerator.format_terminal_summary(report))
        
        if report.unified_diff:
            console.print("\n[bold cyan]Applied Patch Diff:[/bold cyan]")
            syntax = Syntax(report.unified_diff, "diff", theme="monokai", line_numbers=True)
            console.print(syntax)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            console.print(f"\n[green]Saved report to {args.output}[/green]")

    except Exception as e:
        console.print(f"\n[bold red]Fatal Agent Error:[/bold red] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def handle_scan(args):
    repo_path = os.path.abspath(args.repo)
    analyzer = RepositoryAnalyzer(repo_path)
    meta = analyzer.analyze()

    table = Table(title=f"Guardian AI — Repository Analysis: {os.path.basename(repo_path)}")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Primary Language", meta.primary_language)
    table.add_row("Frameworks", ", ".join(meta.frameworks) or "None detected")
    table.add_row("Package Manager", meta.package_manager or "None")
    table.add_row("Test Framework", meta.test_framework or "None")
    table.add_row("Total Files", str(meta.total_files))
    table.add_row("Source Files", str(len(meta.source_files)))
    table.add_row("Test Files", str(len(meta.test_files)))
    table.add_row("Symbols Indexed", str(len(meta.symbols)))

    console.print(table)

def handle_server(args):
    import uvicorn
    console.print(f"[bold cyan]Launching Guardian AI Web Dashboard on http://localhost:{args.port}[/bold cyan]")
    uvicorn.run("guardian_ai.server.app:app", host="0.0.0.0", port=args.port, reload=args.reload)

def main():
    parser = argparse.ArgumentParser(description="Guardian AI — Autonomous Software Engineering Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run autonomous agent on a repository task")
    run_parser.add_argument("--repo", required=True, help="Path to target repository")
    run_parser.add_argument("--task", required=True, help="Natural language engineering task description")
    run_parser.add_argument("--provider", choices=["gemini", "openai", "anthropic", "heuristic"], default=None, help="LLM Provider")
    run_parser.add_argument("--max-iterations", type=int, default=3, help="Max repair iterations")
    run_parser.add_argument("--output", help="Path to save JSON report")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan and analyze repository structure")
    scan_parser.add_argument("--repo", required=True, help="Path to target repository")

    # server command
    server_parser = subparsers.add_parser("server", help="Launch web UI and REST API server")
    server_parser.add_argument("--port", type=int, default=8000, help="Server port")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()
    if args.command == "run":
        handle_run(args)
    elif args.command == "scan":
        handle_scan(args)
    elif args.command == "server":
        handle_server(args)

if __name__ == "__main__":
    main()
