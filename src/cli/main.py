#!/usr/bin/env python3
"""Enhanced CLI for Multi-Tier Orchestrator."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.cli.commands import cmd_doctor, cmd_dry_run, cmd_explain, cmd_init, cmd_stats  # noqa: E402
from src.core.metrics import MetricsCollector  # noqa: E402
from src.core.model_config import MODELS  # noqa: E402
from src.core.orchestrator import LLMOrchestrator  # noqa: E402
from src.core.cost import CostTracker  # noqa: E402

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None


class OrchestratorCLI:
    def __init__(self, use_rich=True):
        self.console = Console() if (use_rich and RICH_AVAILABLE) else None
        self.orchestrator = LLMOrchestrator(str(PROJECT_ROOT))
        self.metrics = MetricsCollector()
        self.use_rich = use_rich and RICH_AVAILABLE

    def print_header(self):
        if self.use_rich:
            self.console.print(
                Panel.fit("[bold blue]Multi-Tier LLM Orchestrator[/bold blue]", border_style="blue")
            )
        else:
            print("=" * 60)
            print("Multi-Tier LLM Orchestrator")
            print("=" * 60)

    def print_status(self, msg, success=True):
        if self.use_rich:
            icon = "[green]\u2713[/green]" if success else "[red]\u2717[/red]"
            self.console.print(f"{icon} {msg}")
        else:
            prefix = "PASS" if success else "FAIL"
            print(f"[{prefix}] {msg}")

    def execute_task(self, task_id, tier, context, output_file=None):
        if self.use_rich:
            self.console.print(f"\n[bold]Executing Task {task_id} with Tier {tier}[/bold]")
            self.console.print(f"Model: [cyan]{MODELS[tier]['model']}[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=self.console,
            ) as progress:
                task = progress.add_task(f"Running {tier}...", total=None)
                try:
                    result = self.orchestrator.execute_task(task_id, tier, context)
                    progress.update(task, completed=True)
                except Exception:
                    progress.update(task, completed=True)
                    raise
        else:
            print(f"\nExecuting Task {task_id} with Tier {tier}")
            print(f"Model: {MODELS[tier]['model']}")
            result = self.orchestrator.execute_task(task_id, tier, context)

        if result["success"]:
            self.print_status(
                f"Completed in {result['duration_seconds']:.1f}s (attempt {result['attempts']})",
                True,
            )
            tr = result.get("tool_results")
            if tr:
                if self.use_rich:
                    self.console.print("\n[bold]Tools:[/bold]")
                for tool in tr.get("tool_results", []):
                    icon = "\u2713" if tool.get("success") else "\u2717"
                    print(f"  {icon} {tool['tool']}('{tool.get('path', '')}')")
            self.metrics.record_task(
                task_id,
                tier,
                True,
                result["duration_seconds"],
                result["attempts"],
                tr.get("tools_executed", 0) if tr else 0,
            )
        else:
            self.print_status(
                f"Failed after {result['attempts']} attempts: {result.get('error', 'Unknown')}",
                False,
            )
            self.metrics.record_task(
                task_id, tier, False, result.get("duration_seconds", 0), result["attempts"]
            )

        if result.get("success") and output_file:
            Path(output_file).write_text(result.get("output", ""))
            if self.use_rich:
                self.console.print(f"\n[dim]Output saved to: {output_file}[/dim]")

        return result

    def print_metrics(self):
        summary = self.metrics.get_summary()
        if self.use_rich:
            self.console.print("\n[bold]Metrics Summary[/bold]")
            table = Table(box=box.SIMPLE)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")
            table.add_row("Total Tasks", str(summary["total_tasks"]))
            table.add_row("Success Rate", f"{summary['overall_success_rate']:.1%}")
            table.add_row("Est. Cost", f"${summary['total_cost_usd']:.4f}")
            self.console.print(table)
        else:
            print("\nMetrics Summary")
            print("-" * 40)
            print(f"Total Tasks: {summary['total_tasks']}")
            print(f"Success Rate: {summary['overall_success_rate']:.1%}")
            print(f"Est. Cost: ${summary['total_cost_usd']:.4f}")


def main():
    p = argparse.ArgumentParser(description="Multi-Tier LLM Orchestrator CLI")
    sub = p.add_subparsers(dest="command")
    
    sub.add_parser("init", help="Interactive setup wizard")
    sub.add_parser("doctor", help="Check system health")
    
    stats_p = sub.add_parser("stats", help="Show cost summary")
    stats_p.add_argument("--export", choices=["json", "csv", "both"],
                         help="Export cost data to file")
    
    explain_p = sub.add_parser("explain", help="Show task execution history")
    explain_p.add_argument("task_id", help="Task ID to explain")
    
    dry_run_p = sub.add_parser("dry-run", help="Preview task without calling LLM")
    dry_run_p.add_argument("description", help="Task description")
    dry_run_p.add_argument("--tier", help="Tier to use")
    
    run_p = sub.add_parser("run", help="Execute a task")
    run_p.add_argument("description", help="Task description")
    run_p.add_argument("--tier", required=True, choices=list(MODELS.keys()))
    run_p.add_argument("--task-id", default="task-1")
    run_p.add_argument("--output")
    run_p.add_argument("--no-rich", action="store_true")
    
    args = p.parse_args()
    
    if args.command == "init":
        sys.exit(cmd_init())
    elif args.command == "doctor":
        sys.exit(cmd_doctor())
    elif args.command == "stats":
        # Handle export option
        if args.export:
            from src.core.config import config_to_budget, load_config
            from src.core.cost import CostTracker, Budget
            
            # Create a default budget if no config exists
            try:
                config = load_config()
                budget = config_to_budget(config)
            except Exception:
                budget = Budget()
                print(f"[INFO] No config found, using default: ${budget.daily_limit_usd}/day")
            
            tracker = CostTracker(budget=budget)
            
            export_path = None
            if args.export == "json":
                export_path = tracker.save_report()
                print(f"JSON report saved to: {export_path}")
            elif args.export == "csv":
                export_path = tracker.export_csv()
                print(f"CSV report saved to: {export_path}")
            elif args.export == "both":
                json_path = tracker.save_report()
                csv_path = tracker.export_csv()
                print(f"JSON report saved to: {json_path}")
                print(f"CSV report saved to: {csv_path}")
            
            sys.exit(0)
        else:
            sys.exit(cmd_stats())
    elif args.command == "explain":
        sys.exit(cmd_explain(args.task_id))
    elif args.command == "dry-run":
        sys.exit(cmd_dry_run(args.description, args.tier))
    elif args.command == "run":
        cli = OrchestratorCLI(use_rich=not args.no_rich)
        cli.print_header()
        context = {"task_description": args.description}
        result = cli.execute_task(args.task_id, args.tier, context, args.output)
        cli.print_metrics()
        sys.exit(0 if result.get("success") else 1)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
