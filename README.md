# MR-Krabs

**Quality-gated multi-tier AI coding agent with judge-based escalation.**

Start with a free local model. Escalate to cloud only when quality demands it.
Return control to the calling agent when all tiers exhaust.

Cost is tracked. Never blocks.

## Agent Quickstart

```bash
git clone https://github.com/o3willard-AI/MR-Krabs.git
cd MR-Krabs
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Write `~/.mrkrabs/config.yaml` (see docs/MODEL_CONFIG.md for examples), then:

```bash
python -m src.core.orchestrator --task "Write a Python bloom filter"
```

## Pipeline

```
L0 (local, free) → L1 (cloud) → L2 (cloud) → Principal (your agent)
      ↑ escalated only if judge rejects quality
```

**All tiers are configurable.** The table below shows one example deployment.
See [docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md) for more.

| Tier | Example | Cost |
|------|---------|------|
| L0-Coder | Local 30B MoE via LiteLLM | Free |
| L1-Coder | Fast cloud model (OpenRouter) | Cloud |
| L2-Coder | Premium cloud model (OpenRouter) | Cloud |
| Judge | Reasoning model (local or cloud) | Varies |
| Principal | — | Your agent |

## How It Works

1. **L0 attempts** via PI coding agent (`pi --mode json`)
2. **Judge evaluates** with anchored rubric (0.0–1.0)
3. **If rejected** → coaching feedback → retry (up to 3x per tier)
4. **If exhausted** → escalate to next tier
5. **Principal reached** → returns structured result to caller

## Programmatic API

```python
from src.core.orchestrator import LLMOrchestrator

orch = LLMOrchestrator()
result = orch.execute_with_judge(
    task_id="rate-limiter",
    context={"task_spec": "Write an async rate limiter"},
    tiers=["l0-coder", "l1-coder", "l2-coder", "principal"],
    max_retries_per_tier=3,
)
```

## Configuration

Everything in `~/.mrkrabs/config.yaml`. No hardcoded models. No hardcoded tiers.

Full reference: [docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md).

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — pipeline design, judge system, PI flow
- [docs/COOKBOOK.md](docs/COOKBOOK.md) — integration recipes + environment variables
- [docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md) — config reference + examples
- [docs/JUDGE.md](docs/JUDGE.md) — judge prompt design + research
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common failure modes and fixes

## License

MIT
