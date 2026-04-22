# Cookbook / Recipes

## 1. Save money on a CrewAI project

```python
from cost_orchestrator import ask

# Wrap your CrewAI agent calls
result = ask("Write a Python function that sorts a list")
print(f"Cost: ${result.cost:.4f}, Tier: {result.tier}")
```

## 2. Track LangChain agent cost per conversation

```python
from cost_orchestrator import ask, get_cost_summary

# Each conversation turn
result = ask("Summarize this document", tier="L0")
print(f"Turn cost: ${result.cost:.4f}")

# End of conversation
summary = get_cost_summary()
print(f"Conversation total: ${summary['daily_total']:.4f}")
```

## 3. Set up a team budget with alerts

```toml
# .cost_orchestrator.toml
[budget]
daily_limit_usd = "50.00"
warning_threshold = "0.8"
failure_mode = "fail_open_with_alert"
emergency_cap_usd = "10.00"
```

```python
from cost_orchestrator import get_budget_remaining

print(f"Remaining: ${get_budget_remaining():.2f}")
```

## 4. Use only local models (no cloud)

```toml
# .cost_orchestrator.toml
[providers.lmstudio]
base_url = "http://localhost:1234/v1"

[tiers]
L0 = { models = ["qwen/qwen3-coder-30b"], max_retries = 3 }
```

```python
from cost_orchestrator import ask

result = ask("Write hello world")
# Cost: $0.0000 (local model)
```

## 5. Optimize for speed, not cost

```toml
# .cost_orchestrator.toml
[tiers]
L0 = { models = ["x-ai/grok-4.1-fast"], max_retries = 1 }
L1 = { models = ["anthropic/claude-sonnet-4.6"], max_retries = 1 }
```

Start with a fast model and escalate to the best model quickly.

## 6. Set per-task cost limits

```python
from cost_orchestrator import ask

# This task won't exceed $0.50
result = ask("Write a simple function", max_cost=0.50)
```

## 7. Dry-run before executing

```bash
orchestrator dry-run "Create auth middleware"
# Shows estimated cost without calling any LLM
```

## 8. Check system health

```bash
orchestrator doctor
# Verifies API keys, config, templates, and connectivity
```
