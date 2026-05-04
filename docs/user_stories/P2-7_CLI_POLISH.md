# Story P2-7: CLI Polish & Developer Experience

**Priority**: P2 (Medium - Improves UX)  
**Estimate**: 0.5 weeks  
**Phase**: Week 16b

---

## User Story

As a developer  
I want a polished, user-friendly CLI experience  
So that I can quickly understand errors, get helpful hints, and use the tool efficiently

---

## Acceptance Criteria

### AC1: Error Message Formatting

- [ ] Errors formatted consistently
- [ ] Error messages include context
- [ ] Error messages suggest fixes
- [ ] Syntax highlighting for code errors
- [ ] Color-coded severity (red=error, yellow=warning, blue=info)

### AC2: Interactive Hints

- [ ] Helpful hints appear on common mistakes
- [ ] Hints suggest next commands
- [ ] Hints link to documentation
- [ ] Hints available for all major commands
- [ ] Hints can be disabled if desired

### AC3: Output Readability

- [ ] Stats output aligned and formatted
- [ ] Tables readable in terminal
- [ ] Long content truncated with `...`
- [ ] Color output optional (--no-color)
- [ ] Monospace fonts for data

### AC4: Command Shortcuts

- [ ] Common commands have shortcuts (e.g., `stats` → `s`)
- [ ] Tab completion for commands
- [ ] Tab completion for options
- [ ] History of recent commands
- [ ] Command suggestions for typos

### AC5: Help Documentation

- [ ] `--help` flag comprehensive
- [ ] Examples in help text
- [ ] Examples runnable directly
- [ ] Link to full docs in help
- [ ] Context-sensitive help

### AC6: Rich Formatting (Optional)

- [ ] Rich library for enhanced output
- [ ] Progress bars for long operations
- [ ] Tables for data presentation
- [ ] Panels for important messages
- [ ] Fallback to plain text if Rich unavailable

---

## Technical Implementation

### Files to Create/Modify

1. `src/cli/formatters.py` - New formatting utilities
2. `src/cli/commands.py` - Enhance with better formatting
3. `src/cli/main.py` - Add shortcuts and enhancements
4. `src/cli/__init__.py` - Export formatters

### Implementation Plan

```python
# src/cli/formatters.py

from typing import Optional
from datetime import datetime

class CLIFormatter:
    """CLI output formatting utilities."""
    
    # Color codes
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    @staticmethod
    def colorize(text: str, color: str, reset: bool = True) -> str:
        """Colorize text."""
        return f"{color}{text}{self.RESET if reset else ''}"
    
    @staticmethod
    def error(message: str) -> str:
        """Format error message."""
        return CLIFormatter.colorize(f"[ERROR] {message}", CLIFormatter.RED)
    
    @staticmethod
    def warning(message: str) -> str:
        """Format warning message."""
        return CLIFormatter.colorize(f"[WARNING] {message}", CLIFormatter.YELLOW)
    
    @staticmethod
    def info(message: str) -> str:
        """Format info message."""
        return CLIFormatter.colorize(f"[INFO] {message}", CLIFormatter.CYAN)
    
    @staticmethod
    def success(message: str) -> str:
        """Format success message."""
        return CLIFormatter.colorize(f"[SUCCESS] {message}", CLIFormatter.GREEN)
    
    @staticmethod
    def hint(message: str) -> str:
        """Format hint message."""
        return CLIFormatter.colorize(f"[HINT] {message}", CLIFormatter.MAGENTA)
    
    @staticmethod
    def format_table(headers: list[str], rows: list[list]) -> str:
        """Format data as a table."""
        if not rows:
            return "No data"
        
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        
        # Build table
        lines = []
        
        # Header
        header_line = " | ".join(
            h.ljust(widths[i]) for i, h in enumerate(headers)
        )
        lines.append(header_line)
        
        # Separator
        separator = "-+-".join("-" * w for w in widths)
        lines.append(separator)
        
        # Rows
        for row in rows:
            line = " | ".join(
                str(cell).ljust(widths[i]) for i, cell in enumerate(row)
            )
            lines.append(line)
        
        return "\n".join(lines)
    
    @staticmethod
    def truncate(text: str, max_length: int = 50) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{int(minutes)}m {secs:.1f}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{int(hours)}h {int(minutes)}m"
    
    @staticmethod
    def format_cost(cost: float, precision: int = 4) -> str:
        """Format cost with proper currency formatting."""
        return f"${cost:.{precision}f}"
    
    @staticmethod
    def format_percentage(value: float, precision: int = 1) -> str:
        """Format percentage."""
        return f"{value:.{precision}f}%"
    
    @staticmethod
    def create_panel(title: str, content: str, width: int = 70) -> str:
        """Create a text panel."""
        border = "━" * width
        return f"{border}\n{title}\n{border}\n{content}\n{border}"
    
    @staticmethod
    def create_section(title: str) -> str:
        """Create a section header."""
        return f"\n{CLIFormatter.BOLD}{title}{CLIFormatter.RESET}\n{'─' * len(title)}\n"

class InteractiveHints:
    """Generate helpful hints for common scenarios."""
    
    @staticmethod
    def for_missing_api_key() -> str:
        """Hint for missing API key."""
        return InteractiveHints.format_hint(
            "No API key found. Run 'export OPENROUTER_API_KEY=\"your-key\"' "
            "or use 'orchestrator init' to set up configuration."
        )
    
    @staticmethod
    def for_budget_exceeded() -> str:
        """Hint for budget exceeded."""
        return InteractiveHints.format_hint(
            "Daily budget exceeded. Run 'orchestrator stats' to see spending, "
            "or increase budget in config file."
        )
    
    @staticmethod
    def for_task_timeout() -> str:
        """Hint for task timeout."""
        return InteractiveHints.format_hint(
            "Task timed out. Try simplifying the task, increasing timeout in config, "
            "or breaking into smaller tasks."
        )
    
    @staticmethod
    def for_provider_not_available() -> str:
        """Hint for unavailable provider."""
        return InteractiveHints.format_hint(
            "Provider not available. Check 'orchestrator doctor' to diagnose "
            "connection issues."
        )
    
    @staticmethod
    def for_tier_escalation() -> str:
        """Hint for frequent tier escalation."""
        return InteractiveHints.format_hint(
            "Task keeps escalating tiers. Try providing more context, "
            "simplifying the task, or starting at a higher tier manually."
        )
    
    @staticmethod
    def format_hint(message: str) -> str:
        """Format a hint message."""
        return CLIFormatter.hint(message)
```

### Enhanced CLI Commands

```python
# src/cli/commands.py

def cmd_stats(export: str | None = None) -> int:
    """Show cost summary with enhanced formatting."""
    from src.core.config import config_to_budget, load_config
    from src.core.cost import CostTracker, Budget
    
    # Handle missing config
    try:
        config = load_config()
        budget = config_to_budget(config)
    except Exception as e:
        print(f"{CLIFormatter.warning('No valid config found, using defaults')}: {e}")
        budget = Budget()
    
    tracker = CostTracker(budget=budget)
    summary = tracker.get_summary()
    
    # Use Rich if available
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        
        console = Console()
        
        # Panel with summary
        panel_content = f"""
{CLIFormatter.bold('Today\'s Spending')}: ${summary['daily_total']:.2f} / ${summary['budget_limit']:.2f} ({summary['budget_used_percent']:.1f}%)
{CLIFormatter.bold('Remaining Budget')}: ${summary['budget_remaining']:.2f}
{CLIFormatter.bold('Total Requests')}: {summary['total_requests']}
{CLIFormatter.bold('Active Reservations')}: {summary['active_reservations']}
"""
        
        if summary['budget_used_percent'] >= 80.0:
            panel_content += f"\n{CLIFormatter.warning('⚠️ Budget Warning:')} {summary['budget_used_percent']:.1f}% used"
        
        console.print(Panel(panel_content, title="Cost Summary", border_style="blue"))
        
        # Table for tier breakdown
        table = Table(title="Tier Breakdown")
        table.add_column("Tier", style="cyan")
        table.add_column("Cost", style="magenta")
        
        for tier, cost in sorted(summary.get("tier_totals", {}).items()):
            table.add_row(tier, f"${cost:.4f}")
        
        console.print(table)
        
        return 0
    
    except ImportError:
        # Fallback to plain text
        return _cmd_stats_plain(export)

def _cmd_stats_plain(export: str | None = None) -> int:
    """Plain text version of stats command."""
    from src.core.config import config_to_budget, load_config
    from src.core.cost import CostTracker, Budget
    
    try:
        config = load_config()
        budget = config_to_budget(config)
    except Exception as e:
        print(f"{CLIFormatter.warning('No valid config found, using defaults')}: {e}")
        budget = Budget()
    
    tracker = CostTracker(budget=budget)
    summary = tracker.get_summary()
    
    print("=" * 70)
    print(CLIFormatter.bold("Cost-Optimized Orchestrator — Cost Summary"))
    print("=" * 70)
    print()
    print(f"Today's spending: ${summary['daily_total']:.2f} / "
          f"${summary['budget_limit']:.2f} ({summary['budget_used_percent']:.1f}%)")
    
    if summary['budget_used_percent'] >= 80.0:
        print(f"\n{CLIFormatter.warning('⚠️ Budget Warning:')} "
              f"{summary['budget_used_percent']:.1f}% of daily limit used")
    
    print(f"Remaining: ${summary['budget_remaining']:.2f}")
    print()
    print(CLIFormatter.bold("Tier breakdown:"))
    
    if summary.get("tier_totals"):
        table_rows = [[tier, f"${cost:.4f}"] 
                     for tier, cost in sorted(summary.get("tier_totals", {}).items())]
        print(CLIFormatter.format_table(["Tier", "Cost"], table_rows))
    else:
        print("  No data yet")
    
    print()
    print(CLIFormatter.bold("Task totals (top 5):"))
    
    task_totals = dict(sorted(summary.get("task_totals", {}).items(), 
                              key=lambda x: x[1], reverse=True)[:5])
    if task_totals:
        table_rows = [[task, f"${cost:.4f}"] for task, cost in task_totals.items()]
        print(CLIFormatter.format_table(["Task", "Cost"], table_rows))
    else:
        print("  No data yet")
    
    print()
    print("=" * 70)
    print(CLIFormatter.info("Export options:"))
    print("  JSON: orchestrator stats --export json")
    print("  CSV:  orchestrator stats --export csv")
    print("  Both: orchestrator stats --export both")
    print()
    
    return 0
```

### Enhanced Help Text

```python
# src/cli/main.py

def setup_argument_parser():
    """Setup argument parser with enhanced help text."""
    import argparse
    
    p = argparse.ArgumentParser(
        description="Cost-Optimized AI Orchestrator - Zero-config cost tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  orchestrator init                      # Interactive setup
  orchestrator doctor                    # Check health
  orchestrator run "task" --tier L0      # Execute task
  orchestrator stats                     # View costs
  orchestrator stats --export json       # Export to JSON

For more information, visit:
  https://github.com/your-org/cost-orchestrator
        """
    )
    
    sub = p.add_subparsers(dest="command", help="Available commands")
    
    # Init command
    sub.add_parser(
        "init",
        help="Interactive setup wizard",
        description="Set up configuration interactively",
        epilog="Creates ~/.cost_orchestrator.toml with your preferences"
    )
    
    # Doctor command
    docs_p = sub.add_parser(
        "doctor",
        help="Check system health and configuration",
        description="""
Run diagnostic checks:
  ✓ API key validation
  ✓ Provider availability
  ✓ Budget configuration
  ✓ Template checking
        """
    )
    
    # Stats command
    stats_p = sub.add_parser(
        "stats",
        help="View cost summary and analytics",
        description="""
Display cost statistics:
  - Today's spending vs. budget
  - Tier-by-tier breakdown
  - Task cost history
  - Budget warnings
        """
    )
    stats_p.add_argument(
        "--export",
        choices=["json", "csv", "both"],
        help="Export cost data to file"
    )
    
    # Explain command
    explain_p = sub.add_parser(
        "explain",
        help="Show task execution history",
        description="""
View why a task escalated through tiers:
  - Original attempt details
  - Error messages
  - Escalation decisions
  - Final successful attempt
        """
    )
    explain_p.add_argument("task_id", help="Task ID to explain")
    
    # Dry-run command
    dry_run_p = sub.add_parser(
        "dry-run",
        help="Preview task cost without executing",
        description="""
Estimate task cost without calling LLM:
  - Estimate tokens
  - Estimate cost per tier
  - Budget availability
  - Expected escalation path
        """
    )
    dry_run_p.add_argument("description", help="Task description")
    dry_run_p.add_argument(
        "--tier",
        help="Specific tier to estimate (default: auto)"
    )
    
    # Run command
    run_p = sub.add_parser(
        "run",
        help="Execute a task with cost tracking",
        description="""
Execute task with automatic cost optimization:
  - Tries cheapest capable model first
  - Escalates on failure
  - Tracks all costs
  - Enforces budget limits
        """
    )
    run_p.add_argument("description", help="Task description")
    run_p.add_argument(
        "--tier",
        required=True,
        choices=["L0-Planner", "L1-Coder", "L2-Coder", "L3-Coder"],
        help="Initial tier to use"
    )
    run_p.add_argument("--task-id", default="task-1", help="Task identifier")
    run_p.add_argument("--output", help="Save output to file")
    run_p.add_argument("--no-rich", action="store_true", help="Disable Rich formatting")
    
    return p
```

---

## Testing Requirements

### Unit Tests (test_formatters.py)

1. `test_colorize` - Color formatting works
2. `test_format_table` - Table formatting correct
3. `test_truncate` - Text truncation works
4. `test_format_duration` - Duration formatted correctly
5. `test_format_cost` - Cost formatting correct
6. `test_format_percentage` - Percentage formatting correct
7. `test_create_panel` - Panel formatting works

### Integration Tests

1. CLI output readable and formatted
2. Error messages helpful and actionable
3. Hints appear for common mistakes
4. Tab completion works
5. Help text comprehensive

---

## Out of Scope

- Real-time progress indicators (except for long operations)
- Custom themes
- Locale-specific formatting
- Accessibility enhancements (WCAG)
- Keyboard shortcuts beyond Tab completion

---

## Dependencies

- P1 complete (core CLI infrastructure)
- All P2-1 through P2-6 (for comprehensive hints)

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Formatting Speed** | <10ms |
| **Table Rendering** | <50ms |
| **Help Text Load** | <5ms |
| **Hint Generation** | <10ms |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Rich formatting tested
- [ ] Plain text fallback tested
- [ ] Documentation updated
- [ ] Examples included

---

## Success Metrics

- **User Satisfaction**: >4/5 rating on CLI UX
- **Error Reduction**: 50% fewer config errors with hints
- **Adoption**: New users onboard in <15 minutes
- **Helpfulness**: 80%+ of hints considered useful

---

*Draft: April 26, 2026*
