# MR-Krabs

**Quality-gated, multi-tier AI orchestrator for code generation.**

MR-Krabs routes coding tasks through tiered escalation (L0 → L1 → L2 → Principal),
with a reasoning-model Judge evaluating every output against anchored rubrics.
Rejected outputs receive coaching feedback for retry — the pipeline only escalates
when retries are exhausted.

## Recommended Infrastructure

**We recommend running MR-Krabs exclusively with
[llama.cpp](https://github.com/ggerganov/llama.cpp).** llama.cpp provides the
most reliable model serving for MR-Krabs' tiered pipeline — it handles tool-call
formats, token streaming, and stop-token behavior correctly. Other backends
(LM Studio, Ollama, vLLM) are known to cause issues with reasoning models,
jinja template injection, and inconsistent tool-call behaviour.

### Quick requirements

- **llama.cpp** running on one or more GPU hosts (our reference setup: two
  dual-RTX-3060 12GB machines at 192.168.101.21 and 192.168.101.23)
- **OpenCode** CLI for the default coder sub-agent (`npm i -g opencode-ai`)
- Python 3.10+ with `pip install -e ".[dev]"`

## Architecture

```
L0 (local llama.cpp, free) → L1 (cloud/model) → L2 (cloud/model) → Principal Agent
       ↑ escalated only if Judge rejects quality
```

- **L0**: Local model on llama.cpp — handles ~75% of tasks at zero cost
- **L1**: First cloud escalation (OpenRouter or secondary local model)
- **L2**: Premium cloud escalation
- **Principal**: Falls back to the calling agent (Hermes, Claude Code, etc.)
- **Judge**: Reasoning model (DeepSeek R1 recommended) — anchored rubric, coaching replies

### Coder sub-agent: OpenCode (default)

By default, each coder tier dispatches to **OpenCode CLI** (`opencode run`),
which handles file writes, bash execution, and multi-file tasks with native
tool use. OpenCode is the recommended sub-agent because it:

- Works reliably with llama.cpp (no jinja template issues)
- Supports decomposed prompting for 30B-class coding models
- Produces verifiable file output with consistent tool-call behavior

**PI Coding Agent** is available as a fallback. Configure `pi_models` in your
config to use PI for specific tiers.

## Quick Start

```bash
git clone https://github.com/o3willard-AI/MR-Krabs.git
cd MR-Krabs
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Create your config (see docs/MODEL_CONFIG.md for examples)
mkdir -p ~/.mrkrabs
cp docs/MODEL_CONFIG.md ~/.mrkrabs/config.yaml  # then edit

# Verify setup
python -m src.validators.templates
python -m src.validators.startup
```

## Configuration

MR-Krabs ships with **zero hardcoded models**. All tiers, providers, and
models are defined in `~/.mrkrabs/config.yaml`. See
[docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md) for example configurations.

### Minimal config (local llama.cpp + OpenRouter Judge)

```yaml
version: "1.0"

providers:
  llama_cpp_23:
    type: openai_compatible
    base_url: http://192.168.101.23:8080/v1
    timeout: 1800
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    timeout: 300

models:
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]

  l0-coder:
    provider: llama_cpp_23
    model: ornith-1.0-35b
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]

  principal:
    roles: [principal]

# OpenCode coder backend (default)
opencode_models:
  l0-coder: llama_cpp_23/ornith-1.0-35b

opencode_timeouts:
  l0-coder: 2400

workflows:
  code:
    tiers: [l0-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
```

## Running Tasks

```python
from src.core.orchestrator import LLMOrchestrator

orch = LLMOrchestrator()
result = orch.execute_with_judge(
    task_id="rate-limiter",
    context={"task_spec": "Write an async rate limiter with Redis backend"},
    tiers=["l0-coder", "l1-coder", "principal"],
    max_retries_per_tier=3,
    project_root="/path/to/target/project",
)
```

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full pipeline design, component map |
| [MODEL_CONFIG.md](docs/MODEL_CONFIG.md) | Config reference with example deployments |
| [JUDGE.md](docs/JUDGE.md) | Judge best practices, coaching reply spec |
| [COOKBOOK.md](docs/COOKBOOK.md) | Integration recipes, env vars |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failure modes and fixes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, testing, PR process |

## Testing

```bash
# Unit tests (fast, no network)
python -m pytest tests/unit/ -q

# All tests including integration
python -m pytest tests/ -q \
    --ignore=tests/integration/test_openrouter_integration.py \
    --ignore=tests/e2e/

# Template validation
python -m src.validators.templates
```

## Model Guidance

| Role | Recommended Class | Why |
|------|------------------|-----|
| **Judge** | Reasoning model (DeepSeek R1, Claude Sonnet) | Anchored rubric scoring needs reasoning |
| **L0 Coder** | 30B+ MoE on llama.cpp (Ornith, Qwen3-Coder) | Free, handles most tasks |
| **L1/L2 Coder** | Cloud fallback (Gemini Flash, Claude Haiku) | Escalation when L0 exhausted |
| **Planner** | Non-reasoning 30B (Qwen3-Coder) | Reasoning models waste budget on CoT |

**Important:** The Judge model must be proportional to the tiers it evaluates.
Using a frontier model to judge a 30B local coder creates an impossible quality bar.
See [JUDGE.md](docs/JUDGE.md) for calibration guidance.

## License

MIT
