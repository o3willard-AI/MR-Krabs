# Cost-Optimized AI Orchestrator

Instead of always using expensive models like GPT-4, this tool tries cheap models first. If they can't do the job, it automatically switches to better (more expensive) models. It tracks how much you're spending and stops if you hit your budget.

## Quickstart

```bash
pip install cost-orchestrator
export OPENROUTER_API_KEY="your-key-here"
```

```python
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")
print(result.output)
print(f"Cost: ${result.cost:.4f}")
```

That's it. No config file, no tier definitions, no infrastructure. Just cheaper LLM calls.

## Before / After

**Before** — every call uses the same expensive model:
```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write auth middleware"}]
)
# Cost: ~$0.12 per call, always
```

**After** — tries cheap models first, escalates only when needed:
```python
from cost_orchestrator import ask
result = ask("Write auth middleware")
# Cost: ~$0.00 on cheap model (87% of tasks)
# Automatically escalates to better models if the cheap one fails
```

## How It Works

1. **Estimate** — guess the task complexity with a cheap model
2. **Check budget** — verify you have spending room
3. **Try cheap first** — route to the cheapest capable model
4. **Retry with simplification** — if it fails, simplify context and retry (up to 3x)
5. **Escalate** — if still failing, try the next more expensive model
6. **Track cost** — update your budget and show savings

## Installation

```bash
pip install cost-orchestrator
```

## Configuration

Zero config required. Set `OPENROUTER_API_KEY` and go.

Optional config file (`.cost_orchestrator.toml`) for tuning:

```toml
version = "1.0"

[budget]
daily_usd = 10.0

[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"
```

Generate one interactively:

```bash
orchestrator init
```

## CLI Commands

```bash
orchestrator init          # Interactive setup
orchestrator doctor        # Check API keys, config, connectivity
orchestrator run "task"    # Execute a task
orchestrator run --dry-run "task"  # Preview cost without calling LLM
orchestrator explain <id>  # See why a task escalated
orchestrator stats         # View spending summary
```

## Documentation

- [How It Works](docs/HOW_IT_WORKS.md) — detailed flow for developers
- [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) — full architecture
- [Technical Design Decisions](docs/architecture/TECHNICAL_DESIGN_DECISIONS.md) — why we made each choice
- [Troubleshooting & FAQ](docs/TROUBLESHOOTING.md) — common issues and fixes
- [Cookbook](examples/) — recipes for common use cases

## What This Is Not

- Not a SaaS — it's a library you run locally
- Not a replacement for CrewAI, LangChain, or other frameworks — it wraps them
- Not a web dashboard — use the CLI for cost reports
- Not a server — no Docker, no PostgreSQL, no Redis required

## License

MIT
