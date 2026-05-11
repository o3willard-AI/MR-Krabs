#!/usr/bin/env python3
"""CLI subcommands: init, doctor, stats, explain, dry-run."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import config_to_budget, load_config  # noqa: E402
from src.core.cost import Budget, CostTracker, TokenCount  # noqa: E402
from src.core.orchestrator import MODELS  # noqa: E402

def cmd_init(config_path: Path | None = None) -> int:
    """Interactive setup wizard."""
    print("=" * 50)
    print("  Cost-Optimized Orchestrator - Setup Wizard")
    print("=" * 50)
    print()
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        print("✓ Found OPENROUTER_API_KEY in environment")
        use_env = input("Use environment variable for API key? [Y/n]: ").strip().lower()
        if use_env in ("", "y", "yes"):
            api_key_env = "OPENROUTER_API_KEY"
        else:
            api_key_env = input("Enter env var name: ").strip() or "OPENROUTER_API_KEY"
    else:
        api_key_env = "OPENROUTER_API_KEY"
        print("Enter your OpenRouter API key:")
        print("  Get one at: https://openrouter.ai/keys")
        key = input("API key: ").strip()
        if key:
            os.environ["OPENROUTER_API_KEY"] = key
    
    has_lm = input("\n✓ Do you have LM Studio running locally? [y/N]: ").strip().lower()
    use_lm = has_lm in ("y", "yes")
    
    budget_str = input("✓ Daily budget in USD [10.00]: ").strip()
    daily_budget = budget_str or "10.00"
    
    config = {
        "version": "1.0",
        "budget": {
            "daily_limit_usd": daily_budget,
            "failure_mode": "fail_open_with_alert",
            "emergency_cap_usd": "5.00",
        },
        "providers": {
            "openrouter": {
                "api_key_env": api_key_env,
            },
        },
    }
    
    if use_lm:
        config["providers"]["lmstudio"] = {
            "base_url": "http://localhost:1234/v1",
        }
        print("\n✓ LM Studio will be configured as free tier")
    
    if config_path is None:
        config_path = Path.home() / ".cost_orchestrator.toml"
    
    try:
        import tomllib  # noqa: F401
    except ImportError:
        print("Warning: tomllib not available (Python 3.11+). Using JSON config.")
        config_path = config_path.with_suffix(".json")
    
    if config_path.suffix == ".toml":
        content = _dict_to_toml(config)
    else:
        content = json.dumps(config, indent=2)
    
    config_path.write_text(content)
    print(f"\n✓ Configuration written to {config_path}")
    
    print("\nSetup complete!")
    print("\nRun your first task:")
    print("  from cost_orchestrator import ask")
    print("  result = ask('Write a hello world in Python')")
    print("  print(result.output)")
    
    return 0


def cmd_doctor() -> int:
    """Diagnostic command to check system health."""
    print("Cost-Optimized Orchestrator — Doctor")
    print("=" * 50)
    print()

    all_ok = True

    # Check environment variables for each provider
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        print("[PASS] OPENROUTER_API_KEY is set")
    else:
        print("[FAIL] OPENROUTER_API_KEY is not set")
        print("       Fix: export OPENROUTER_API_KEY='your-key'")
        all_ok = False

    lm_host = os.environ.get("LM_STUDIO_HOST", "http://localhost:1234/v1")
    print(f"[INFO] LM Studio host: {lm_host} (optional)")

    # Check available tiers
    available_tiers = []
    for tier, config in MODELS.items():
        provider = config.get("provider")
        if provider == "openrouter":
            if openrouter_key:
                available_tiers.append(tier)
        elif provider == "lmstudio":
            # LM Studio always considered available (connection tested later)
            available_tiers.append(tier)
        else:
            available_tiers.append(tier)

    print(f"[INFO] Available tiers: {', '.join(available_tiers) if available_tiers else 'None'}")

    if not available_tiers:
        print("[FAIL] No LLM providers configured. Set OPENROUTER_API_KEY or LM_STUDIO_HOST.")
        all_ok = False

    # Check configuration
    budget = None
    try:
        config = load_config()
        print("[PASS] Configuration loaded")

        budget = config_to_budget(config)
        print(
            f"[PASS] Budget: ${budget.daily_limit_usd:.2f}/day "
            f"(mode: {budget.failure_mode.value})"
        )
    except Exception as e:
        print(f"[FAIL] Configuration error: {e}")
        all_ok = False

    # Check templates
    templates_dir = PROJECT_ROOT / "templates"
    if templates_dir.exists():
        templates = list(templates_dir.glob("*.md"))
        if templates:
            print(f"[PASS] {len(templates)} prompt template(s) found")
        else:
            print(f"[WARN] No prompt templates found in {templates_dir}")
    else:
        print("[WARN] Templates directory not found")

    # Check cost tracker initialization
    try:
        from src.core.cost import Budget, CostTracker

        _tracker = CostTracker(budget=budget if budget else Budget())
        print("[PASS] Cost tracker initialized")
    except Exception as e:
        print(f"[FAIL] Cost tracker error: {e}")
        all_ok = False

    print()
    if all_ok:
        print("All checks passed!")
        return 0
    else:
        print("Some checks failed. See above for fixes.")
        return 1


def cmd_dry_run(description: str, tier: str | None = None) -> int:
    """Preview task execution without calling any LLM."""
    config = load_config()
    budget = config_to_budget(config)
    tracker = CostTracker(budget=budget)

    selected_tier = tier or "L0"
    model = MODELS.get(selected_tier, MODELS.get("L0-Planner", {}))
    model_name = model.get("model", "unknown")

    prompt_tokens = len(description) // 4
    estimated_completion = max(prompt_tokens, 200)

    tokens = TokenCount(prompt_tokens=prompt_tokens, completion_tokens=estimated_completion)
    min_cost = tracker.calculate_cost(model_name, tokens)

    print("Dry run results:")
    print(f"  Task: {description}")
    print(f"  Initial tier: {selected_tier} ({model_name})")
    print(f"  Estimated tokens: ~{prompt_tokens} prompt + ~{estimated_completion} completion")
    print(
        f"  Estimated cost: ${min_cost:.4f} (L0) to "
        f"${min_cost * 10:.4f} (if escalated)"
    )
    print(f"  Budget remaining: ${budget.daily_limit_usd - tracker.daily_total:.2f}")
    print()
    print("No LLM API calls were made.")
    return 0


def cmd_stats(export: str | None = None) -> int:
    """Show cost summary."""
    from src.core.config import config_to_budget, load_config
    
    # Handle case where no config exists
    try:
        config = load_config()
        budget = config_to_budget(config)
    except Exception as e:
        print(f"[WARN] No valid config found, using defaults: {e}")
        from src.core.cost import Budget
        budget = Budget()
    
    tracker = CostTracker(budget=budget)
    
    summary = tracker.get_summary()
    print("=" * 60)
    print("  Cost-Optimized Orchestrator — Cost Summary")
    print("=" * 60)
    print()
    print(f"Today's spending: ${summary['daily_total']:.2f} / "
          f"${summary['budget_limit']:.2f} ({summary['budget_used_percent']:.1f}%)")
    
    # P1-5: Display budget warning if at 80% threshold
    if summary['budget_used_percent'] >= 80.0:
        print(f"\n[!] BUDGET WARNING: {summary['budget_used_percent']:.1f}% of daily limit used")
    
    print(f"Remaining: ${summary['budget_remaining']:.2f}")
    print()
    print("Tier breakdown:")
    for tier, cost in sorted(summary.get("tier_totals", {}).items()):
        print(f"  {tier}: ${cost:.4f}")
    print()
    print("Task totals (top 5):")
    task_totals = dict(sorted(summary.get("task_totals", {}).items(), 
                              key=lambda x: x[1], reverse=True)[:5])
    for task, cost in task_totals.items():
        print(f"  {task}: ${cost:.4f}")
    print()
    
    # P1-6: Export functionality
    if export:
        export_path = None
        if export == "json":
            export_path = tracker.save_report()
            print(f"✓ Saved JSON report: {export_path}")
        elif export == "csv":
            export_path = tracker.export_csv()
            print(f"✓ Saved CSV report: {export_path}")
        elif export == "both":
            json_path = tracker.save_report()
            csv_path = tracker.export_csv()
            print(f"✓ Saved JSON report: {json_path}")
            print(f"✓ Saved CSV report: {csv_path}")
        else:
            print(f"Invalid export format: {export}")
            print("Valid formats: json, csv, both")
            return 1
    
    if not export:
        print("=" * 60)
        print("Export options:")
        print("  JSON: orchestrator stats --export json")
        print("  CSV:  orchestrator stats --export csv")
        print("  Both: orchestrator stats --export both")
        print()
    
    return 0


def cmd_explain(task_id: str, log_dir: Path | None = None) -> int:
    """Show step-by-step execution history for a task."""
    if log_dir is None:
        log_dir = PROJECT_ROOT / "docs" / "workflow"

    handoffs_dir = log_dir / "handoffs"
    escalations_dir = log_dir / "escalations"

    if not handoffs_dir.exists() and not escalations_dir.exists():
        print("No execution logs found. Run tasks first to generate logs.")
        return 1

    safe_task_id = task_id.replace(".", "_")
    handoff_files = (
        sorted(handoffs_dir.glob(f"{safe_task_id}-*.json")) if handoffs_dir.exists() else []
    )
    escalation_files = (
        sorted(escalations_dir.glob(f"{safe_task_id}-*.json")) if escalations_dir.exists() else []
    )

    if not handoff_files and not escalation_files:
        print(f"No logs found for task: {task_id}")
        return 1

    print(f"Task: {task_id}")
    print()

    for f in escalation_files:
        data = json.loads(f.read_text())
        print(f"  Attempt: {data.get('tier', '?')} - FAILED")
        print(f"    Reason: {data.get('error', 'Unknown')}")
        print(f"    Attempts: {data.get('attempts', '?')}")
        print("    Action: Escalated to next tier")
        print()

    for f in handoff_files:
        data = json.loads(f.read_text())
        if data.get("success"):
            print(f"  Attempt: {data.get('tier', '?')} - SUCCESS")
            print(f"    Duration: {data.get('duration_seconds', 0):.1f}s")
            print(f"    Attempt #: {data.get('attempt', '?')}")
            print()

    total_cost = sum(
        json.loads(f.read_text()).get("duration_seconds", 0)
        for f in handoff_files + escalation_files
    )
    print(f"Total duration: {total_cost:.1f}s")
    return 0


def _dict_to_toml(d: dict, indent: int = 0) -> str:
    """Simple dict to TOML converter for config files."""
    lines = []
    prefix = "  " * indent
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}[{key}]")
            lines.append(_dict_to_toml(value, indent + 1))
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{prefix}{key} = {value}")
        else:
            lines.append(f'{prefix}{key} = "{value}"')
    return "\n".join(lines)


# =============================================================================
# Report Commands (P4-5: Daily Cost Reporting)
# =============================================================================

def cmd_daily_report(days: int = 1) -> int:
    """Generate daily cost report."""
    from datetime import date, timedelta
    from decimal import Decimal
    from src.core.metrics import MetricsCollector
    from src.reports.daily_report import DailyCostReportGenerator
    
    print("=" * 60)
    print("  Cost-Optimized Orchestrator - Daily Report")
    print("=" * 60)
    print()
    
    # Load config
    config = load_config()
    daily_limit = config_to_budget(config).daily_limit_usd
    
    # Get metrics
    collector = MetricsCollector()
    summary = collector.get_daily_summary()
    
    if not summary or summary.get('total_cost') is None:
        print("No cost data available. Run some tasks first.")
        return 0
    
    # Generate report
    generator = DailyCostReportGenerator()
    warning_threshold = Decimal(str(config.get('warning_threshold', 0.8)))
    report = generator.generate(summary, daily_limit, warning_threshold, days)
    print(report)
    
    return 0


def cmd_efficiency_report() -> int:
    """Generate tier efficiency report."""
    from src.core.metrics import MetricsCollector
    from src.reports.efficiency import TierEfficiencyAnalyzer
    from src.reports.trend_analysis import TrendAnalyzer
    
    print("=" * 60)
    print("  Cost-Optimized Orchestrator - Tier Efficiency Report")
    print("=" * 60)
    print()
    
    # Get metrics
    collector = MetricsCollector()
    tier_metrics = collector.get_tier_metrics()
    
    if not tier_metrics:
        print("No tier data available. Run some tasks first.")
        return 0
    
    # Analyze efficiency
    analyzer = TierEfficiencyAnalyzer()
    analyses = analyzer.analyze_all_tiers(tier_metrics)
    
    # Print tier rankings
    print("Tier Efficiency Rankings:")
    print("-" * 40)
    
    for analysis in analyzer.rank_by_efficiency(analyses):
        print(f"  {analysis.tier_name}:")
        print(f"    Usage: {analysis.usage_count} tasks")
        print(f"    Cost: ${analysis.total_cost:.2f} (${analysis.avg_cost_per_task:.4f}/task)")
        print(f"    Success: {analysis.success_rate:.1%}")
        print(f"    Efficiency Score: {analysis.efficiency_score}/100")
        print()
    
    # Get suggestions
    suggestions = analyzer.get_optimization_suggestions(analyses)
    if suggestions:
        print("Optimization Suggestions:")
        print("-" * 40)
        for suggestion in suggestions:
            priority_marker = {"high": "!", "medium": "~", "low": "."}[suggestion["priority"]]
            print(f"  [{priority_marker}] {suggestion['tier']}: {suggestion['message']}")
    
    return 0


def cmd_trend_report(days: int = 7) -> int:
    """Generate cost trend report."""
    from datetime import date, timedelta
    from src.core.metrics import MetricsCollector
    from src.reports.trend_analysis import TrendAnalyzer
    
    print("=" * 60)
    print("  Cost-Optimized Orchestrator - Cost Trend Report")
    print("=" * 60)
    print()
    
    # Get metrics
    collector = MetricsCollector()
    
    if days == 7:
        daily_costs = collector.get_daily_costs_7day()
    elif days == 30:
        daily_costs = collector.get_daily_costs_30day()
    else:
        daily_costs = collector.get_daily_costs_7day()
    
    if not daily_costs:
        print("No cost data available. Run some tasks first.")
        return 0
    
    # Analyze trends
    analyzer = TrendAnalyzer()
    
    if len(daily_costs) >= 7:
        analysis = analyzer.analyze_7_day_trend(daily_costs[-7:])
    else:
        analysis = analyzer.analyze_7_day_trend(daily_costs)
    
    # Print trend analysis
    print("Trend Analysis:")
    print("-" * 40)
    print(f"  Period: {analysis.period_start} to {analysis.period_end}")
    print(f"  Total Cost: ${analysis.total_cost:.2f}")
    print(f"  Average Daily: ${analysis.avg_daily_cost:.2f}")
    print(f"  Day-over-Day Change: {analysis.day_over_day_change:+.1%}")
    
    if days >= 14 and len(daily_costs) >= 14:
        print(f"  Week-over-Week Change: {analysis.week_over_week_change:+.1%}")
    
    print()
    
    if analysis.has_spending_spike:
        print("⚠️  SPENDING SPIKE DETECTED!")
        print(f"  Costs increased by {analysis.day_over_day_change:.0%} compared to yesterday.")
        print()
    
    # Print recommendations
    recommendations = analyzer.generate_trend_recommendations(analysis)
    if recommendations:
        print("Recommendations:")
        print("-" * 40)
        for rec in recommendations:
            icon = {"high": "!", "medium": "~", "low": "."}[rec["priority"]]
            print(f"  [{icon}] {rec['message']}")
    
    return 0


def cmd_optimization_report() -> int:
    """Generate comprehensive optimization report."""
    from datetime import date, timedelta
    from decimal import Decimal
    from src.core.config import config_to_budget, load_config
    from src.core.metrics import MetricsCollector
    from src.reports.efficiency import TierEfficiencyAnalyzer
    from src.reports.trend_analysis import TrendAnalyzer
    
    print("=" * 60)
    print("  Cost-Optimized Orchestrator - Optimization Report")
    print("=" * 60)
    print()
    
    # Load config
    config = load_config()
    daily_limit = config_to_budget(config).daily_limit_usd
    
    # Get metrics
    collector = MetricsCollector()
    summary = collector.get_summary()
    
    if not summary:
        print("No cost data available. Run some tasks first.")
        return 0
    
    # Budget status
    print("Budget Status:")
    print("-" * 40)
    total_cost = summary.get('total_cost', Decimal("0.00"))
    budget = daily_limit
    usage_pct = total_cost / budget if budget > 0 else Decimal("0.00")
    print(f"  Daily Limit: ${budget:.2f}")
    print(f"  Current Spend: ${total_cost:.2f}")
    print(f"  Budget Used: {usage_pct:.1%}")
    
    if usage_pct >= Decimal("0.80"):
        print("  ⚠️  WARNING: Over 80% of daily budget used!")
    elif usage_pct >= Decimal("0.95"):
        print("  ⚠️  CRITICAL: Over 95% of daily budget used!")
    print()
    
    # Tier efficiency analysis
    print("Tier Efficiency:")
    print("-" * 40)
    
    tier_metrics = collector.get_tier_metrics()
    if tier_metrics:
        analyzer = TierEfficiencyAnalyzer()
        analyses = analyzer.analyze_all_tiers(tier_metrics)
        
        for analysis in analyzer.rank_by_efficiency(analyses)[:3]:  # Top 3
            print(f"  {analysis.tier_name}:")
            print(f"    ${analysis.avg_cost_per_task:.4f}/task, "
                  f"{analysis.success_rate:.1%} success, "
                  f"score: {analysis.efficiency_score}")
    else:
        print("  No tier data available")
    print()
    
    # Trend analysis
    print("Recent Trends (7-day):")
    print("-" * 40)
    daily_costs = collector.get_daily_costs_7day()
    if daily_costs:
        trend_analyzer = TrendAnalyzer()
        trend = trend_analyzer.analyze_7_day_trend(daily_costs[-7:])
        print(f"  Average: ${trend.avg_daily_cost:.2f}/day")
        print(f"  Trend: {trend.day_over_day_change:+.1%} vs yesterday")
    else:
        print("  No trend data available")
    print()
    
    # Optimization suggestions
    print("Optimization Suggestions:")
    print("-" * 40)
    
    if tier_metrics:
        suggestions = analyzer.get_optimization_suggestions(analyses)
        for suggestion in suggestions[:5]:  # Top 5 suggestions
            icon = {"high": "!", "medium": "~", "low": "."}[suggestion["priority"]]
            print(f"  [{icon}] {suggestion['tier']}: {suggestion['message']}")
    
    if not suggestions:
        print("  No optimization suggestions at this time.")
    
    print()
    print("=" * 60)
    
    return 0
