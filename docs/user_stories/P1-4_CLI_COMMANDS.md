# Story P1-4: Complete CLI Commands

**Priority**: P1 (High)  
**Estimate**: 4 days  
**Phase**: Week 2

---

## User Story

As a developer  
I want a complete set of CLI commands to interact with the orchestrator  
So that I can quickly validate my setup, estimate costs, and execute tasks from the terminal

---

## Acceptance Criteria

### AC1: `orchestrator init` - Interactive Setup
- [ ] Prompts for `OPENROUTER_API_KEY` (with hidden input)
- [ ] Offers to create `.cost_orchestrator.toml` config file
- [ ] Suggests default budget ($10/day) with option to change
- [ ] Tests API key connectivity immediately
- [ ] Writes configuration to `~/.cost_orchestrator.toml`
- [ ] Shows success/failure status of each step
- [ ] Exits with code 0 on success, 1 on failure

**User Flow:**
```bash
$ orchestrator init

Multi-Tier LLM Orchestrator Setup
==================================

1. OpenRouter API Key
   Please enter your OpenRouter API key (or press Enter to skip):
   [hidden input]

2. Budget Configuration
   Daily budget limit: $10.00
   [10.00] Enter to accept, or type custom amount:
   
3. LM Studio Local Model
   Would you like to configure LM Studio for local models?
   [Y/n] 

✓ Setup complete! Configuration saved to ~/.cost_orchestrator.toml
```

### AC2: `orchestrator doctor` - System Health Check
- [ ] Checks `OPENROUTER_API_KEY` environment variable
- [ ] Tests OpenRouter API connectivity with a lightweight call
- [ ] Checks LM Studio connectivity (if configured)
- [ ] Validates `.cost_orchestrator.toml` config file (if exists)
- [ ] Checks Python version (requires >= 3.11)
- [ ] Reports available models and their status
- [ ] Exits with code 0 if all checks pass, 1 if any fail

**Output Format:**
```bash
$ orchestrator doctor

Multi-Tier LLM Orchestrator — System Health Check
==================================================

✓ Python version: 3.12.1 (required: >= 3.11)
✓ OpenRouter API key: configured
✓ OpenRouter connectivity: OK (tested with qwen/qwen3.5-397b-a17b)
✓ LM Studio: not configured (optional)
✓ Config file: ~/.cost_orchestrator.toml (valid)

Available Models:
  L0-Coder: qwen/qwen3-coder-30b (LM Studio, local)
  L1-Coder: x-ai/grok-4.1-fast (OpenRouter, $0.008/1k tokens)
  L2-Coder: minimax/minimax-m2.7 (OpenRouter, $0.0008/1k tokens)
  L3-Coder: anthropic/claude-sonnet-4.6 (OpenRouter, $0.018/1k tokens)

Budget: $10.00/day (0.0% used today)

Status: HEALTHY ✓
```

### AC3: `orchestrator run` - Execute Task
- [ ] Required argument: `--tier` (choices: all tier names)
- [ ] Optional argument: `--task-id` (default: "task-1")
- [ ] Optional argument: `--description` (task to execute)
- [ ] Optional argument: `--output` (write output to file)
- [ ] Optional argument: `--no-rich` (disable colorful output)
- [ ] Shows progress spinner during execution
- [ ] Reports success/failure with duration
- [ ] Shows tool execution results (file_read/file_write)
- [ ] Exits with code 0 on success, 1 on failure

**Usage:**
```bash
$ orchestrator run --tier L1-Coder --description "Write a hello world in Python"

Multi-Tier LLM Orchestrator
============================

Executing Task task-1 with Tier L1-Coder
Model: x-ai/grok-4.1-fast
⠋ Running L1-Coder...

✓ Completed in 12.3s (attempt 1)

Tools:
✓ file_write('/tmp/hello.py')

Budget: $10.00/day ($0.0008 used today, 0.0%)

[0.00%] task-1: SUCCESS
```

### AC4: `orchestrator dry-run` - Cost Estimation
- [ ] Required argument: task description
- [ ] Optional argument: `--tier` (default: auto-select cheapest)
- [ ] Estimates token count from task description
- [ ] Shows estimated cost range (min/max)
- [ ] Shows which tier would be used
- [ ] Shows number of LLM calls estimated
- [ ] Does NOT call any LLM API
- [ ] Uses LLM to estimate complexity (if available)

**Usage:**
```bash
$ orchestrator dry-run "Build a REST API with authentication"

Multi-Tier LLM Orchestrator — Dry Run
======================================

Task: Build a REST API with authentication

Estimated Complexity: HIGH
Recommended Tier: L3-Coder (anthropic/claude-sonnet-4.6)

Estimated Cost Breakdown:
  - Task complexity estimation: $0.0001 (1 attempt)
  - Planning phase (L0): $0.0002 (1 attempt)
  - Implementation (L3): $0.0150 (1 attempt)
  
Total Estimated Cost: $0.0153

This is approximately 87% cheaper than using GPT-4o directly ($0.12).

Note: Actual cost may vary based on response length.
```

### AC5: `orchestrator explain <task_id>` - Execution History
- [ ] Required argument: `task_id`
- [ ] Searches `docs/workflow/escalations/` for task log
- [ ] Shows all tier attempts with success/failure
- [ ] Shows escalation decisions and reasons
- [ ] Shows context simplification attempts
- [ ] Shows cost breakdown per attempt
- [ ] Shows duration and any errors
- [ ] If not found, shows similar recent tasks

**Usage:**
```bash
$ orchestrator explain task-123

Multi-Tier LLM Orchestrator — Execution History
================================================

Task ID: task-123
Total Cost: $0.0125
Total Duration: 45.2s

Attempt History:
─────────────────────────────────────────────────────────

Attempt 1: L0-Coder (qwen/qwen3-coder-30b)
  Status: FAILED
  Duration: 8.3s
  Reason: file_write failed: Permission denied
  Context Simplified: Yes (70% of original)

Attempt 2: L0-Coder (qwen/qwen3-coder-30b)
  Status: FAILED  
  Duration: 9.1s
  Reason: file_write failed: Permission denied
  Context Simplified: Yes (40% of original)

Attempt 3: L1-Coder (x-ai/grok-4.1-fast)
  Status: SUCCESS
  Duration: 12.4s
  Cost: $0.0008
  Tools: file_write('/tmp/app.py') ✓

Escalation: L0 → L1 (tier_exhausted)

Total Cost: $0.0008 (L1) + $0.0004 (L0 retries) = $0.0012
```

### AC6: `orchestrator stats` - Cost Summary Dashboard
- [ ] Shows total cost for current session
- [ ] Shows daily budget limit and remaining
- [ ] Shows budget usage percentage
- [ ] Breaks down costs by tier
- [ ] Breaks down costs by task
- [ ] Shows total number of tasks executed
- [ ] Shows average cost per task
- [ ] Shows success rate
- [ ] Optional: export to JSON/CSV

**Usage:**
```bash
$ orchestrator stats

Multi-Tier LLM Orchestrator — Cost Summary
==========================================

Session Statistics
─────────────────────────────────────────────────────────
Total Cost: $2.45
Daily Budget: $10.00
Remaining: $7.55 (75.5%)
Tasks Executed: 18
Success Rate: 94.4%

Cost by Tier
─────────────────────────────────────────────────────────
L0-Coder:   $0.12 (4.9%) - 12 tasks
L1-Coder:   $0.45 (18.4%) - 8 tasks
L2-Coder:   $0.89 (36.3%) - 5 tasks
L3-Coder:   $0.99 (40.4%) - 3 tasks

Top Tasks by Cost
─────────────────────────────────────────────────────────
task-456: $0.15
task-789: $0.12
task-321: $0.10

[Export to JSON/CSV] (coming soon)
```

---

## Technical Implementation

### Files to Create/Modify
1. `src/cli/commands.py` - Implement all command functions
2. `src/cli/main.py` - Already exists, update argument parsing
3. `src/core/exceptions.py` - Add `ConfigNotFoundError`

### Command Implementation Skeleton

```python
# src/cli/commands.py

import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from dataclasses import dataclass

try:
    from src.core.orchestrator import LLMOrchestrator, MODELS
    from src.core.cost import CostTracker, Budget
    from src.core.metrics import MetricsCollector
    from src.core.exceptions import ConfigNotFoundError
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False

console = Console()

@dataclass
class Config:
    """Configuration loaded from file."""
    openrouter_api_key: Optional[str] = None
    daily_budget_usd: float = 10.0
    lmstudio_base_url: Optional[str] = None

def load_config() -> Config:
    """Load config from ~/.cost_orchestrator.toml."""
    config_path = Path.home() / ".cost_orchestrator.toml"
    if not config_path.exists():
        raise ConfigNotFoundError("No config file found. Run 'orchestrator init' first.")
    
    # Parse TOML
    import tomli
    with open(config_path, "rb") as f:
        data = tomli.load(f)
    
    return Config(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        daily_budget_usd=data.get("budget", {}).get("daily_usd", 10.0),
        lmstudio_base_url=data.get("providers", {}).get("lmstudio", {}).get("base_url"),
    )

def cmd_init():
    """Interactive setup wizard."""
    console.print(Panel("Multi-Tier LLM Orchestrator Setup", style="bold blue"))
    
    # Step 1: API Key
    console.print("\n1. OpenRouter API Key")
    api_key = getpass.getpass("Enter your OpenRouter API key (or press Enter to skip): ")
    
    # Step 2: Budget
    console.print("\n2. Budget Configuration")
    default_budget = 10.0
    budget_input = input(f"Daily budget limit: ${default_budget:.2f} [default]: ")
    daily_budget = float(budget_input) if budget_input.strip() else default_budget
    
    # Step 3: LM Studio
    console.print("\n3. LM Studio (optional)")
    lmstudio_enabled = input("Configure LM Studio for local models? [y/N]: ").strip().lower() == "y"
    lmstudio_url = None
    if lmstudio_enabled:
        lmstudio_url = input("LM Studio base URL [http://127.0.0.1:1234/v1]: ")
        lmstudio_url = lmstudio_url or "http://127.0.0.1:1234/v1"
    
    # Write config
    config_path = Path.home() / ".cost_orchestrator.toml"
    config_content = f"""# Cost Orchestrator Configuration
# Generated: {datetime.now().isoformat()}

[budget]
daily_usd = {daily_budget}

[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"
"""
    
    if lmstudio_url:
        config_content += f"""
[providers.lmstudio]
base_url = "{lmstudio_url}"
"""
    
    config_path.write_text(config_content)
    
    # Test API key
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key
        # ... test connectivity
        console.print("\n[green]✓ Setup complete![/green]")
    else:
        console.print("\n[yellow]⚠ Setup complete (without API key)[/yellow]")
    
    return 0

def cmd_doctor():
    """System health check."""
    console.print(Panel("Multi-Tier LLM Orchestrator — System Health Check", style="bold blue"))
    
    success_count = 0
    failure_count = 0
    
    # Check Python version
    import sys
    if sys.version_info >= (3, 11):
        console.print("[green]✓[/green] Python version: " + f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        success_count += 1
    else:
        console.print("[red]✗[/red] Python version: " + f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} (required: >= 3.11)")
        failure_count += 1
    
    # Check API key
    if os.environ.get("OPENROUTER_API_KEY"):
        console.print("[green]✓[/green] OpenRouter API key: configured")
        success_count += 1
    else:
        console.print("[red]✗[/red] OpenRouter API key: not configured")
        failure_count += 1
    
    # Test API connectivity
    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            # ... test connectivity
            console.print("[green]✓[/green] OpenRouter connectivity: OK")
            success_count += 1
        except Exception as e:
            console.print(f"[red]✗[/red] OpenRouter connectivity: FAILED ({e})")
            failure_count += 1
    
    # ... more checks
    
    # Summary
    console.print("\n" + "=" * 50)
    if failure_count == 0:
        console.print("[green]Status: HEALTHY ✓[/green]")
        return 0
    else:
        console.print(f"[red]Status: UNHEALTHY ({failure_count} issue(s))[/red]")
        return 1

def cmd_run(args):
    """Execute a task."""
    orchestrator = LLMOrchestrator(project_root=...)
    result = orchestrator.execute_task(
        task_id=args.task_id,
        tier=args.tier,
        context={"description": args.description}
    )
    
    # ... format and display result
    return 0 if result["success"] else 1

def cmd_dry_run(description: str, tier: Optional[str] = None):
    """Preview cost without calling LLM."""
    # Estimate token count
    estimated_tokens = len(description.split()) * 1.5  # Rough estimate
    
    # Select tier
    if not tier:
        tier = "L0-Coder"  # Cheapest
    
    model = MODELS[tier]["model"]
    pricing = CostTracker.MODEL_COSTS.get(model, {"prompt": 0.001, "completion": 0.001})
    
    estimated_cost = (estimated_tokens / 1000) * (pricing["prompt"] + pricing["completion"])
    
    console.print(f"Estimated Cost: ${estimated_cost:.6f}")
    return 0

def cmd_explain(task_id: str):
    """Show task execution history."""
    # Search for task log in docs/workflow/escalations/
    # ...
    return 0

def cmd_stats():
    """Show cost summary dashboard."""
    # Load cost tracker state
    # ...
    return 0
```

---

## Testing Requirements

### Unit Tests (test_cli_commands.py)
1. `test_cmd_init_creates_config` - Config file created correctly
2. `test_cmd_init_tests_api_key` - Tests API connectivity
3. `test_cmd_doctor_all_pass` - All checks pass with valid setup
4. `test_cmd_doctor_api_key_missing` - Reports missing API key
5. `test_cmd_run_success` - Returns exit code 0 on success
6. `test_cmd_run_failure` - Returns exit code 1 on failure
7. `test_cmd_dry_run_estimates_cost` - Returns reasonable estimate
8. `test_cmd_explain_finds_log` - Finds task log by ID
9. `test_cmd_stats_shows_summary` - Correctly aggregates costs

### Integration Tests
1. Full workflow: init → doctor → run → stats
2. CLI with real OpenRouter API key
3. Verify rich output renders correctly

---

## User Experience Goals

- **Fast**: Commands complete in <5 seconds (except `run`)
- **Informative**: Clear error messages with actionable next steps
- **Consistent**: All commands use same styling and exit codes
- **Discoverable**: `--help` shows usage for all commands

---

## Out of Scope
- Password protection for config file
- Multi-profile configuration
- Cloud sync of configuration
- Real-time cost streaming

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] CLI works with and without Rich library
- [ ] Help text accurate and complete
- [ ] Code reviewed and approved

---

## Dependencies
- Requires `src/core/orchestrator.py` to be complete
- Requires `src/core/cost.py` `CostTracker` and `Budget`
- Requires `src/core/exceptions.py` for custom exceptions
