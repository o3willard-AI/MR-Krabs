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
from src.core.cost import CostTracker, TokenCount  # noqa: E402
from src.core.orchestrator import MODELS  # noqa: E402


def cmd_init(config_path: Path | None = None) -> int:
    """Interactive setup wizard."""
    print("Welcome to Cost-Optimized Orchestrator!")
    print()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        print("Found OPENROUTER_API_KEY in environment.")
        use_env = input("Use environment variable for API key? [Y/n]: ").strip().lower()
        if use_env in ("", "y", "yes"):
            api_key_env = "OPENROUTER_API_KEY"
        else:
            api_key_env = input("Enter env var name: ").strip() or "OPENROUTER_API_KEY"
    else:
        api_key_env = "OPENROUTER_API_KEY"
        key = input("Enter your OpenRouter API key (or env var name): ").strip()
        if key and not key.isupper():
            os.environ["OPENROUTER_API_KEY"] = key

    has_lm = input("\nDo you have LM Studio running locally? [y/N]: ").strip().lower()
    use_lm = has_lm in ("y", "yes")

    budget_str = input("\nDaily budget in USD [10.00]: ").strip()
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

    if config_path is None:
        config_path = Path.cwd() / ".cost_orchestrator.toml"

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
    print(f"\nConfiguration written to {config_path}")

    gitignore = Path.cwd() / ".gitignore"
    ignore_entry = config_path.name
    if gitignore.exists():
        if ignore_entry not in gitignore.read_text():
            with open(gitignore, "a") as f:
                f.write(f"\n{ignore_entry}\n")
    else:
        gitignore.write_text(f"{ignore_entry}\n")
    print(f"Added {ignore_entry} to .gitignore")

    print("\nRun your first task:")
    print("  from cost_orchestrator import ask")
    print('  result = ask("Write a hello world in Python")')
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
            f"[PASS] Budget: ${float(budget.daily_limit_usd):.2f}/day "
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
        f"  Estimated cost: ${float(min_cost):.4f} (L0) to "
        f"${float(min_cost) * 10:.4f} (if escalated)"
    )
    print(f"  Budget remaining: ${float(budget.daily_limit_usd - tracker.daily_total):.2f}")
    print()
    print("No LLM API calls were made.")
    return 0


def cmd_stats() -> int:
    """Show cost summary."""
    from src.core.config import config_to_budget, load_config

    config = load_config()
    budget = config_to_budget(config)
    tracker = CostTracker(budget=budget)

    summary = tracker.get_summary()
    print(
        f"Today's spending: ${summary['daily_total']:.2f} / "
        f"${summary['budget_limit']:.2f} ({summary['budget_used_percent']:.1f}%)"
    )
    print()
    print("Tier breakdown:")
    for tier, cost in summary.get("tier_totals", {}).items():
        print(f"  {tier}: ${cost:.4f}")
    print()
    print("Task totals:")
    for task, cost in summary.get("task_totals", {}).items():
        print(f"  {task}: ${cost:.4f}")
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
