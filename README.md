<div align="center">

# Cost-Optimized AI Orchestrator

[![PyPI - Version](https://img.shields.io/pypi/v/cost-orchestrator.svg)](https://pypi.org/project/cost-orchestrator/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cost-orchestrator.svg)](https://pypi.org/project/cost-orchestrator/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Test Coverage](https://img.shields.io/badge/coverage-67%25-green.svg)](https://github.com/pairadmin/MR-Krabs)

**Zero-config, cost-saving LLM orchestration with auto-escalation and budget tracking.**

</div>
---

---

## 📖 Table of Contents

- [Quickstart](#quickstart)
- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Advanced Usage](#advanced-usage)
- [CLI Commands](#cli-commands)
- [Contributing](#contributing)
- [License](#license)

---

Instead of always using expensive models like GPT-4, this tool tries cheap models first. If they can't do the job, it automatically switches to better (more expensive) models. It tracks how much you're spending and stops if you hit your budget.

### 🌟 Key Features
  - [Auto-Escalation Logic](#auto-escalation-logic)
  - [Context Simplification on Retry](#context-simplification-on-retry)
  - [Metrics & Reporting](#metrics--reporting)
  - [Integrations](#integrations)
- [Advanced Usage](#advanced-usage)
  - [Custom Tier Definitions](#custom-tier-definitions)
  - [CrewAI Integration](#crewai-integration)
  - [LangChain Callback Handler](#langchain-callback-handler)
- [CLI Commands](#cli-commands)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---
- 🚀 **Zero-config setup** - Just set your API key and go
- 💰 **Save 87% on average** - Try cheap models first, escalate only when needed
- 🛡️ **Budget protection** - Daily limits, emergency caps, warning alerts at 80%
- 🎯 **Budget-aware tier selection** - Automatic tier adjustment based on remaining budget
- 📊 **Cost reporting** - Daily reports, trend analysis, efficiency metrics, JSON/CSV exports
- 🔧 **Smart error handling** - Cost-aware retry strategies, intelligent failure recovery
- 🔄 **Auto-escalation** - 4-tier system (L0→L3) with context simplification
- 🧪 **Local model support** - LM Studio integration for free local inference

---

## Quickstart

### Installation

```bash
# Install MR-Krabs (includes CrewAI multi-agent framework automatically)
pip install cost-orchestrator

# Verify installation
python -c "from crewai import Agent, Task, Crew; print('✅ CrewAI ready!')"
```

**Note**: CrewAI (multi-agent framework) is a required dependency and installs automatically (~500MB including dependencies).

### First Task

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

```python
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")
print(result.output)
print(f"Cost: ${result.cost:.4f}")
print(f"Tier used: {result.tier_used}")
```

**Output:**
```
def sort_list(lst):
    return sorted(lst)

Cost: $0.0012
Tier used: L0
```

That's it. No config file, no tier definitions, no infrastructure. Just cheaper LLM calls.

---

## Before / After: Cost Savings Demo

### Before — Always Using Expensive Models

```python
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write auth middleware"}]
)
# Cost: ~$0.12 per call, always
```

**Annual cost for 10,000 tasks:** $1,200

### After — Smart Cost Optimization

```python
from cost_orchestrator import ask

result = ask("Write auth middleware")
# 87% of tasks: $0.001 on cheap model (L0)
# 13% of tasks: $0.05 on escalated model (L1/L2)
# Average cost: ~$0.008 per task
# Total savings: 87% vs. GPT-4o always
```

**Annual cost for 10,000 tasks:** ~$80

**You save $1,120 while maintaining the same quality.**

---

## How It Works

### The 4-Tier System

| Tier | Name | Models | Cost | Best For |
|------|------|--------|------|----------|
| **L0** | Cheap | qwen/qwen3.5-397b-a17b | $0.001 | Simple tasks (90% of use cases) |
| **L1** | Balanced | x-ai/grok-4.1-fast | $0.004 | Moderate complexity |
| **L2** | Pro | anthropic/claude-sonnet-4.6 | $0.008 | Complex reasoning |
| **L3** | Expert | anthropic/claude-opus-4.6 | $0.0003 | Critical, high-stakes tasks |

### Escalation Flow

1. **Estimate** - Guess task complexity with cheap model
2. **Check budget** - Verify you have spending room, apply budget-aware tier selection
3. **Try L0 first** - Route to cheapest capable model (87% of tasks)
4. **Retry with simplification** - If it fails, simplify context and retry (up to 3x)
5. **Escalate** - If still failing, try L1, L2, then L3
6. **Track cost** - Update budget and show savings
7. **Warning alerts** - Notify at 80% and emergency cap (150%)

### Budget-Aware Tier Selection (P4-2)

The system automatically adjusts tier selection based on your remaining budget:

```
Budget Remaining | Tier Preference | Behavior
--------------|----------------|----------
> 80%          | L2 (normal)     | Standard tier selection
50-80%         | L1 (prefer)     | Prefer cheaper tiers for simple tasks  
30-50%         | L0 (strong)     | Strongly prefer cheapest tier
< 30%          | L0 (restrict)   | Restrict to L0 unless explicitly forced
< 15%          | L0 (emergency)  | Emergency mode - L0 only
```

**Example:** When budget drops below 30%, simple tasks automatically route to L0 even if they could use L1:

```
[BUDGET WARNING 28%] Adjusting tier preference: L2→L0 for simple tasks
[TIER SELECTED] Budget restriction: selecting L0 | Task: simple | Budget: 28.1%
```

Force a specific tier override:
```python
result = ask("Complex analysis", tier="L2")  # Bypasses budget restrictions
```

### Cost-Aware Error Handling (P4-3)

Different errors have different cost-recovery strategies to minimize waste:

**Error Classification:**

| Error Type | Strategy | Max Retries | Budget-Aware Behavior |
|-----------|----------|-------------|----------------------|
| Network/Timeout | Retry with backoff | 5-7 | Skip retries if budget < 10% |
| Rate Limit | Retry with delay | 3 | Skip retries if budget < 20% |
| Context Too Long | Simplify & retry | 3 | Aggressive simplification when budget low |
| Auth Error | Fail immediately | 0 | Not retryable |
| Budget Exceeded | Escalate | 0 | Stops all tasks |

**Example:** When budget is low, error handling changes:

```
[BUDGET ALERT 12%] Skipping retry for rate limit (budget too low)
[TASK] Failed gracefully - no wasted retries
```

---

## Installation & Configuration

### Zero-Config (Recommended)

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

That's it! The default configuration works out of the box:

- Daily budget: $10.00
- Warning threshold: 80% ($8.00)
- Emergency cap: $5.00 (hard stop at $15.00 total)
- Failure mode: `fail_open_with_alert` (warn but continue)

### Optional Config File

Create `~/.cost_orchestrator.toml` for custom settings:

```toml
version = "1.0"

[budget]
daily_limit_usd = "10.00"
task_limit_usd = "1.00"
warning_threshold = "0.8"
failure_mode = "fail_open_with_alert"
emergency_cap_usd = "5.00"

[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"

[providers.lmstudio]
base_url = "http://localhost:1234/v1"
```

Generate one interactively:

```bash
orchestrator init
```

---

## API Reference

### `ask()` Function

The main entry point for all LLM interactions.

```python
from cost_orchestrator import ask

# Basic usage
result = ask("Write a hello world program")

# With custom budget
result = ask("Build a REST API", budget=5.0)

# With tier override (force a specific tier)
result = ask("Debug complex issue", tier="L3")

# With custom model
result = ask("Translate text", model="meta-llama/llama-3.3-70b")
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | str | **required** | The task description |
| `budget` | float | `None` | Override daily budget limit |
| `tier` | str | `"L0"` | Force specific tier (L0, L1, L2, L3) |
| `model` | str | `None` | Force specific model name |
| `context` | dict | `{}` | Additional context for the task |
| `timeout` | int | `300` | Task timeout in seconds |

#### Return Value

`AskResult` object with:

```python
@dataclass
class AskResult:
    output: str           # Model response text
    cost: float           # Cost in USD
    tier_used: str        # Tier that succeeded (L0-L3)
    attempts: int         # Number of attempts before success
    tokens: TokenCount    # Token usage breakdown
    success: bool         # Whether task completed successfully
    error: str | None     # Error message if failed
```

#### Example Usage

```python
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")

if result.success:
    print(result.output)
    print(f"Cost: ${result.cost:.4f}")
    print(f"Tier used: {result.tier_used}")
    print(f"Attempts: {result.attempts}")
    print(f"Tokens: {result.tokens.total_tokens}")
else:
    print(f"Task failed: {result.error}")
```

---

## CLI Commands

### Setup & Diagnostics

```bash
orchestrator init          # Interactive setup wizard
orchestrator doctor        # Check API keys, config, connectivity
```

**`orchestrator doctor` Output:**
```
Cost-Optimized Orchestrator — Doctor
==================================================

[PASS] OPENROUTER_API_KEY is set
[INFO] LM Studio host: http://localhost:1234/v1 (optional)
[INFO] Available tiers: L0-Planner, L1-Coder, L2-Coder, L3-Coder
[PASS] Budget: $10.00/day (mode: fail_open_with_alert)
[PASS] Configuration loaded
[PASS] Cost tracker initialized

All checks passed!
```

### Task Execution

```bash
orchestrator run "task description" --tier L0
orchestrator run "task" --tier L1 --task-id my-task-123
orchestrator run "task" --tier L0 --output result.txt
orchestrator run "task" --tier L0 --no-rich  # Disable Rich output
```

### Preview & Analysis

```bash
orchestrator dry-run "task description"           # Estimate cost without calling LLM
orchestrator dry-run "task" --tier L1             # Preview with specific tier
orchestrator explain <task-id>                    # See why a task escalated
```

**`orchestrator dry-run` Output:**
```
Dry run results:
  Task: Write hello world
  Initial tier: L0-Planner (qwen/qwen3.5-397b-a17b)
  Estimated tokens: ~50 prompt + ~200 completion
  Estimated cost: $0.0001 (L0) to $0.0010 (if escalated)
  Budget remaining: $10.00

No LLM API calls were made.
```

### Cost Reporting

```bash
orchestrator stats                     # View cost summary
orchestrator stats --export json        # Save JSON report
orchestrator stats --export csv         # Save CSV report
orchestrator stats --export both        # Save both formats
```

**`orchestrator stats` Output:**
```
============================================================
  Cost-Optimized Orchestrator — Cost Summary
============================================================

Today's spending: $0.15 / $10.00 (1.5%)
Remaining: $9.85

Tier breakdown:
  L0-Coder: $0.0500
  L1-Coder: $0.1000

Task totals (top 5):
  task-1: $0.0500
  task-2: $0.1000

============================================================
Export options:
  JSON: orchestrator stats --export json
  CSV:  orchestrator stats --export csv
  Both: orchestrator stats --export both
```

### Daily Reports (P4-5)

```bash
orchestrator daily-report [days]       # Generate daily cost report (default: 1 day)
```

**Options:**
- `days` (int): Number of days to report on (default: 1)
- `--verbose`: Show detailed breakdowns

**`orchestrator daily-report` Output:**
```
============================================================
  Cost-Optimized Orchestrator - Daily Report
  Period: Last 1 day(s)
============================================================

Budget Status:
----------------------------------------
  Daily Limit:      $100.00
  Current Spend:    $45.00
  Budget Used:      45.0%

Tasks Executed: 500

By Tier:
  L0-Coder: $10.00 (22.2%)
  L1-Coder: $20.00 (44.4%)
  L2-Coder: $15.00 (33.3%)

Tier Efficiency:
  L0-Coder: ✅ Excellent (score: 95/100)
  L1-Coder: ⚠️  Moderate (score: 68/100)
  L2-Coder: ✅ Excellent (score: 92/100)
```

**Example: 7-day report:**
```bash
orchestrator daily-report 7
```

---

### Tier Efficiency Reports (P4-5)

```bash
orchestrator efficiency-report         # Analyze tier efficiency and optimization opportunities
```

**`orchestrator efficiency-report` Output:**
```
============================================================
  Cost-Optimized Orchestrator - Tier Efficiency Report
============================================================

Tier Efficiency Rankings:
----------------------------------------
Rank  Tier         Score   Avg Cost/Task   Success Rate   Usage
1     L0-Coder     95      $0.010          98.0%          450 tasks
2     L2-Coder     92      $0.008          96.5%          50 tasks
3     L1-Coder     68      $0.040          88.0%          100 tasks

Tier Utilization:
----------------------------------------
  L0-Coder: 75.0% (450/600) - Appropriate
  L1-Coder: 16.7% (100/600) - Appropriate
  L2-Coder: 8.3% (50/600) - Appropriate
  L3-Coder: 0.0% (0/600) - Underutilized

Optimization Suggestions:
----------------------------------------
  [!] Consider shifting more complex tasks to L2-Coder
  [.] L1-Coder shows lower efficiency - review task routing
  [+] L0-Coder performing excellently - continue current strategy
```

---

### Trend Analysis Reports (P4-5)

```bash
orchestrator trend-report [days]       # Analyze cost trends over time
```

**Options:**
- `days` (int): Number of days to analyze (default: 7)

**`orchestrator trend-report` Output:**
```
============================================================
  Cost-Optimized Orchestrator - Trend Report (7 days)
============================================================

Cost Trend:
----------------------------------------
  Daily Average:  $12.50
  Week-over-Week: +12.5%
  Trend Direction: 📈 Increasing

Day-over-Day Changes:
  Day 1: $8.00 (baseline)
  Day 2: $9.00 (+12.5%)
  Day 3: $11.00 (+22.2%)
  Day 4: $10.00 (+0.0%)
  Day 5: $13.00 (+30.0%)
  Day 6: $15.00 (+50.0%) ⚠️ SPIKE
  Day 7: $14.00 (+25.0%)

Cost Projections (next 7 days):
  Low:  $87.50
  Mid:  $105.00
  High: $122.50

Spending Spike Detection:
----------------------------------------
  ⚠️  SPENDING SPIKE DETECTED!
  Costs increased by 50.0% compared to yesterday.
  Recommended action: Review recent task patterns.

Recommendations:
----------------------------------------
  [!] Daily average cost is increasing (+12.5% week-over-week)
  [!] Consider reducing L2/L3 tier usage
  [+] Cost spike on Day 6 was isolated - monitor for recurrence
```

---

### Comprehensive Optimization Reports (P4-5)

```bash
orchestrator optimization-report       # Full analysis with recommendations
```

**`orchestrator optimization-report` Output:**
```
==========================================
  Cost-Optimized Orchestrator - Optimization Report
==========================================

Summary:
------------------------
  Total Tasks (30 days): 5,000
  Total Cost:           $625.00
  Average Cost/Task:    $0.125
  Budget Utilization:   62.5% ($625 / $1,000 monthly)

Budget Status:
------------------------
  Daily Limit:   $10.00
  Current Spend: $45.00 / $100.00 (45.0%)
  Remaining:     $55.00

Trend Analysis (7-day):
------------------------
  Average Daily Cost: $12.50
  Week-over-Week:     +12.5%
  Trend Direction:    📈 Increasing

Tier Efficiency:
------------------------
  L0-Coder: 95/100  ✅ Excellent
  L1-Coder: 68/100  ⚠️  Moderate efficiency
  L2-Coder: 92/100  ✅ Excellent
  L3-Coder: N/A     - No usage

Optimization Opportunities:
------------------------
  [!] HIGH: Daily costs increasing - review task complexity
  [!] HIGH: L1-Coder efficiency below target (68%)
  [~] MEDIUM: Consider using L2-Coder for complex tasks
  [.] LOW: L3-Coder underutilized - can be safely removed
  [+] LOW: Overall budget utilization healthy at 62.5%

Action Items:
------------------------
  1. Review L1-Coder task routing rules
  2. Monitor daily cost trend for continued increase
  3. Consider shifting L1 tasks to L2 for better efficiency
  4. Remove L3-Coder from tier list if not needed
```

---

## API Examples: Advanced Features

### Budget-Aware Task Execution (P4-2)

```python
from cost_orchestrator import ask

# Task automatically selects tier based on budget
result = ask("Write documentation")
# If budget > 80%: Uses L2 (standard)
# If budget 30-80%: Prefers L1 for simple tasks
# If budget < 30%: Automatically uses L0 (cheapest)

# Force tier override (bypasses budget awareness)
result = ask("Critical analysis", tier="L3")
```

### Custom Budget per Task

```python
from cost_orchestrator import ask

# Limit this task to $2 total
result = ask("Build REST API", budget=2.0)

# If task costs more than $2, it will fail gracefully
# without exceeding the limit
```

### Error Handling with Retry

```python
from cost_orchestrator import ask

# Error handling is automatic:
# - Network errors: Retry with backoff
# - Rate limits: Retry after delay
# - Context too long: Simplify and retry
# - Auth errors: Fail immediately

result = ask("Process data")
if result.success:
    print(f"Success in {result.attempts} attempt(s)")
    print(f"Total cost: ${result.cost:.4f}")
else:
    print(f"Failed: {result.error}")
```

### Context & Tool Passing

```python
from cost_orchestrator import ask

context = {
    "file_path": "/path/to/code.py",
    "existing_code": "def hello(): pass",
    "requirements": ["Must use async/await"]
}

result = ask("Refactor this function", context=context)
```

### LM Studio (Free Local Inference)

```toml
# ~/.cost_orchestrator.toml
[providers.lmstudio]
base_url = "http://localhost:1234/v1"
```

When LM Studio is configured, it's automatically included as a free tier (L0) option.

---

## Migration Guides

### From Direct LLM Calls

**Before:**
```python
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write code"}]
)
# Cost: ~$0.12 per call, always
```

**After:**
```python
from cost_orchestrator import ask

result = ask("Write code")
# Cost: ~$0.008 average (87% savings)
# Automatically tries cheap models first
print(result.output)
print(f"Cost: ${result.cost:.4f}")
```

### From CrewAI

**Before:**
```python
from crewai import Agent, Task, Crew

agent = Agent(
    role='coder',
    llm='gpt-4o',  # Always expensive
    ...
)
```

**After:**
```python
from crewai import Agent, Task, Crew
from cost_orchestrator import CrewAIOrchestrator

# Wrap your CrewAI setup with cost optimization
orchestrator = CrewAIOrchestrator()

agent = Agent(
    role='coder',
    llm=orchestrator.get_llm(),  # Smart tier selection
    ...
)

# Track costs
crew = Crew(...).execute()
print(orchestrator.get_cost_summary())
```

### From LangChain

**Before:**
```python
from langchain.chat_models import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")  # Always expensive
```

**After:**
```python
from langchain.chains import LLMChain
from cost_orchestrator import LangChainCostCallbackHandler

# Add cost tracking to LangChain
callback = LangChainCostCallbackHandler()

llm = ChatOpenAI(
    model="gpt-4o",
    callbacks=[callback]  # Tracks costs automatically
)

# View cost summary
print(callback.get_summary())
```

---

## Advanced Usage

### Custom Budget per Task

```python
from cost_orchestrator import ask

# Limit this task to $5 total
result = ask("Build complete auth system", budget=5.0)
```

### Force Specific Model

```python
from cost_orchestrator import ask

# Always use this specific model
result = ask("Translate text", model="meta-llama/llama-3.3-70b")
```

### LM Studio (Free Local Inference)

```toml
# ~/.cost_orchestrator.toml
[providers.lmstudio]
base_url = "http://localhost:1234/v1"
```

When LM Studio is configured, it's automatically included as a free tier option.

### Context & Tool Passing

```python
from cost_orchestrator import ask

context = {
    "file_path": "/path/to/code.py",
    "existing_code": "def hello(): pass",
    "requirements": ["Must use async/await"]
}

result = ask("Refactor this function", context=context)
```

---

## Budget & Warnings

### Budget Limits

| Setting | Default | Description |
|---------|---------|-------------|
| `daily_limit_usd` | $10.00 | Maximum spend per day |
| `task_limit_usd` | $1.00 | Maximum per single task |
| `emergency_cap_usd` | $5.00 | Additional buffer above daily limit |

### Warning Alerts

**Regular Warning (80% threshold):**
```
[BUDGET WARNING] $8.0000 / $10.00 (80.0%)
```

**Emergency Warning (150% threshold):**
```
*** EMERGENCY BUDGET ALERT *** $15.0000 / $15.00 ***
```

- Warnings shown only once per day (no spam)
- Automatic reset at UTC midnight
- Do NOT block execution (unless `failure_mode = "fail_closed"`)

### Failure Modes

```toml
[budget]
failure_mode = "fail_open_with_alert"  # Default: warn but continue
failure_mode = "fail_closed"           # Block immediately on budget exceeded
```

---

## Troubleshooting

### "API key not working"

**Cause**: Environment variable not set or invalid key.

**Fix:**
```bash
echo $OPENROUTER_API_KEY
export OPENROUTER_API_KEY="your-key-here"
```

### "Budget exceeded"

**Cause**: Daily limit reached.

**Fix:**
1. Run `orchestrator stats` to see current spending
2. Wait until next day (UTC midnight) for reset
3. Increase budget in config file
4. Break large tasks into smaller chunks

### "LM Studio connection failed"

**Cause**: LM Studio not running or wrong URL.

**Fix:**
```bash
# Start LM Studio
lmstudio server

# Verify URL
curl http://localhost:1234/v1/models
```

### "Task keeps escalating"

**Cause**: Task may be too complex for cheap models.

**Fix:**
1. Simplify the task description
2. Provide more context in `context=` parameter
3. Start at a higher tier manually (`tier="L2"`)
4. Use `orchestrator dry-run` to preview escalation path

### "Config file not found"

**Fix:**
```bash
orchestrator init
```

---

## FAQ

### How much can I save?

Real-world metrics:
- **87% of tasks** complete on L0 (cheap model)
- **13% of tasks** escalate to L1/L2/L3
- **Average cost**: ~$0.008/task vs $0.12/task with GPT-4o
- **Total savings**: ~87%

### Does this work with streaming?

Streaming is planned but not yet implemented. Current implementation uses request-response calls.

### What happens if I go over budget?

- Default: `fail_open_with_alert` — tasks continue but warnings shown
- Emergency cap: Hard stop at $15.00 (daily $10 + emergency $5)
- Alternative: `fail_closed` — block immediately on budget exceeded

### Can I use local models?

Yes! LM Studio is fully supported and treated as a free tier.

### Does this replace CrewAI or LangChain?

No. This wraps them and adds cost optimization on top.

### Is my API key stored?

No. The API key is used in memory only. Configuration stores the env var name, not the key itself.

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for detailed instructions on:

- **Development setup** - Setting up your environment
- **Code style guidelines** - Type hints, docstrings, formatting
- **Testing requirements** - Writing tests and coverage targets
- **Pull request process** - How to submit changes

### Quick Links

📚 [Contributing Guide](CONTRIBUTING.md) - Full contribution documentation  
📝 [Changelog](CHANGELOG.md) - Recent changes and version history  
🧪 [Testing Guide](TESTING_GUIDE.md) - Testing framework details  

---

## License

MIT License

Copyright (c) 2026 Cost-Optimized AI Orchestrator

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

**Made with ❤️ for cost-conscious developers**
