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

- **llama.cpp** running on one or more GPU hosts (reference setup: dual-RTX-3060
  12GB at 192.168.101.23 running Qwen3.6-27B Q4_K_M)
- **PI Coding Agent** for the recommended coder sub-agent (`npm i -g @nousresearch/pi`)
- Python 3.10+ with `pip install -e ".[dev]"`

## Architecture

```
Human writes spec → MR-Krabs loop (coder → judge → retry/accept → escalate)
                         ↑ fully autonomous                    ↓
                    Human reviews final output         Principal Agent (fallback)
```

- **L0**: Local model on llama.cpp — handles ~75% of tasks at zero cost
- **L1**: First cloud escalation (OpenRouter or secondary local model)
- **L2**: Premium cloud escalation
- **Principal**: Falls back to the calling agent (Hermes, Claude Code, etc.)
- **Judge**: Evaluates every output against the spec with anchored rubrics and
  coaching replies. Can be the same model as the coder — peer judging produces
  calibrated scores; disproportionate judge models create impossible quality bars.

### Coder sub-agent: PI Coding Agent (recommended)

**PI is the recommended sub-agent for multi-file tasks.** On a 27B model at 49K
context, PI writes **11 complete files per pass** vs OpenCode's 1-3. PI streams
tool calls as JSONL and writes files directly — no "analysis mode" collapse on
large specs. OpenCode remains available as a fallback for single-file or simple
tasks.

See [`docs/reference-configs/winning-config-jul2026.yaml`](docs/reference-configs/winning-config-jul2026.yaml)
for the proven single-model config (all three roles on Qwen3.6-27B, $0/run).

## Value Proposition: MR-Krabs vs Frontier Model

Why run a local pipeline when you could just ask Claude Sonnet?

**The difference is who runs the iteration loop.** A frontier model doesn't get
complex multi-file tasks right in one shot. Without a judge, **you** are the
retry mechanism — reviewing output, writing feedback, re-prompting, repeating.
MR-Krabs automates that loop. You write the spec once and get judge-verified output.

### Worked example: 17-file Flask admin panel (kiosk challenge)

This task was run through MR-Krabs 7 times during development and once to
completion. Below is a comparison of the final successful run against an
estimated frontier-model workflow for the same task.

| Phase | MR-Krabs (local, $0 inference) | Claude Sonnet 4.6 ($3/M in, $15/M out) |
|-------|-------------------------------|----------------------------------------|
| **Write spec** | Human: 15-20 min | Human: 15-20 min |
| **Initial generation** | PI writes 11 files in Pass 1 (~30K tokens generated, $0) | Model generates ~17 files (~25K tokens output, $0.38) |
| **Quality check** | Judge evaluates against spec, scores 0.75, provides coaching | **Human reviews all 17 files** — 10-15 min |
| **Retry / revision** | PI retries with coaching, writes remaining 6 files in Pass 2 (~15K tokens, $0) | Human writes feedback, re-prompts. Model regenerates with growing context (~$0.50). **Repeat 1-3×** |
| **Final review** | Human reviews judge-verified output: 5-10 min | Human does final review: 5-10 min |
| **Total tokens consumed** | ~150K (coder input/output + judge evaluation) | ~120K (3 iterations with growing conversation) |
| **Total cost** | **$0.00** | **~$2.50** |
| **Human active time** | **25-30 min** (spec + final review only) | **45-60 min** (spec + review every iteration + write feedback) |
| **Wall clock** | 39 min (mostly unattended) | 20-40 min (active throughout) |

### Where the gap widens

| Factor | Impact |
|--------|--------|
| **Task size** | 50+ files: frontier model hits output limits, needs more iterations. MR-Krabs splits into 5+ passes — same cost, linear time. |
| **Iterations** | Every frontier model retry costs $0.50-1.00 and 10-15 min of your time. MR-Krabs retries are free and autonomous. |
| **Experimentation** | Want to try a different approach? MR-Krabs: re-run at $0. Frontier: pay again. |
| **Privacy** | MR-Krabs keeps your code and spec on your hardware. Frontier: everything goes to the API provider. |
| **Consistency** | MR-Krabs produces judge-calibrated output every time. Frontier: quality varies with prompt phrasing and model version. |

### The loop is the product

MR-Krabs isn't cheaper per-token — at $2.50/run, the frontier model is already
cheap. MR-Krabs is cheaper per **iteration**. The judge automates what you'd
otherwise do manually: read the output, compare it to the spec, write feedback,
and decide whether to accept or retry. For a 17-file project that took 7
experimental runs to get right, that's $0 vs ~$17.50 and hours of saved review time.

## Quick Start

```bash
git clone https://github.com/o3willard-AI/MR-Krabs.git
cd MR-Krabs
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Create your config (see docs/MODEL_CONFIG.md for examples)
mkdir -p ~/.mrkrabs
cp docs/reference-configs/winning-config-jul2026.yaml ~/.mrkrabs/config.yaml

# Verify setup
python -m src.validators.templates
python -m src.validators.startup
```

## Configuration

MR-Krabs ships with **zero hardcoded models**. All tiers, providers, and
models are defined in `~/.mrkrabs/config.yaml`. See
[docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md) for example configurations.

### Minimal config (local llama.cpp, single model — all roles)

```yaml
version: "1.0"

providers:
  local-23:
    type: openai_compatible
    base_url: http://192.168.101.23:1234/v1
    api_key: dummy
    timeout: 1800

models:
  judge:
    provider: local-23
    model: "qwen3.6-27b-q4_k_m"
    temperature: 0.1
    max_tokens: 16384
    roles: [judge]

  l0-coder:
    provider: local-23
    model: "qwen3.6-27b-q4_k_m"
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]
    tools: [file_write, file_read]

  principal:
    roles: [principal]

# PI coder backend (recommended for multi-file tasks)
pi_models:
  l0-coder: bakeoff23/qwen3.6-27b-q4

pi_timeouts:
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
| [HARDWARE-TIERS.md](docs/HARDWARE-TIERS.md) | Three-tier hardware guide (12/24/36 GB VRAM) |
| [MODEL_CONFIG.md](docs/MODEL_CONFIG.md) | Config reference with example deployments |
| [JUDGE.md](docs/JUDGE.md) | Judge best practices, coaching reply spec |
| [COOKBOOK.md](docs/COOKBOOK.md) | Integration recipes, env vars |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failure modes and fixes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, testing, PR process |
| [reference-configs/](docs/reference-configs/) | Proven configs with rationale |

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

| Role | Recommended | Why |
|------|------------|-----|
| **L0 Coder** | 27B+ MoE on llama.cpp (Qwen3.6-27B, Ornith-35B) | Free, handles multi-file tasks via PI |
| **Judge** | Same model as coder OR reasoning model of similar class | Peer judging = calibrated; disproportionate judge = impossible bar |
| **L1/L2 Coder** | Cloud fallback (DeepSeek V4 Flash, Mimo V2.5) | Escalation when L0 exhausted |
| **Orchestrator** | Non-reasoning model (Qwen3.6-27B with `--reasoning off`) | Reasoning models waste 95%+ tokens on CoT; adapter only reads content |

**Proven single-model config:** Qwen3.6-27B Q4_K_M handles all three roles
(coder via PI, judge, orchestrator) with calibrated scoring. See
[winning-config-jul2026.yaml](docs/reference-configs/winning-config-jul2026.yaml).

## License

MIT
