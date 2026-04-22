# How It Works

When you call `orchestrator.execute()` or `ask()`, here's what happens:

1. **Estimate** — We estimate the task complexity using a cheap model to gauge difficulty
2. **Check budget** — We verify you have budget remaining before making any LLM calls
3. **Try cheap first** — We route your task to the cheapest capable model (L0)
4. **Retry with simplification** — If it fails, we simplify the context and retry (up to 3 times)
5. **Escalate** — If still failing, we try the next more expensive model (L1 → L2 → L3)
6. **Track cost** — We record the cost, update your budget, and show you the savings

That's it. The tier system, context simplification, circuit breakers, and budget enforcement all happen behind the scenes. You just get cheaper LLM calls with automatic quality fallback.

## Why This Saves Money

Most tasks (70-90%) can be handled by cheap or free models. The expensive models are only used when the cheap ones genuinely can't do the job. By trying cheap first and escalating only when necessary, you avoid paying premium prices for work that doesn't need it.

## Key Concepts (Optional Reading)

- **Tiers (L0-L3)**: Cost levels from free/cheap to premium. L0 is tried first, L3 is the last resort.
- **Escalation**: Moving up to a more expensive tier when the current one fails.
- **Context Simplification**: Reducing prompt size on retries to fit within model limits.
- **Circuit Breaker**: Temporarily skipping models that are experiencing failures.
- **Budget**: Your daily spending limit. The system stops when you hit it.

For full technical details, see [System Architecture](architecture/SYSTEM_ARCHITECTURE.md).
