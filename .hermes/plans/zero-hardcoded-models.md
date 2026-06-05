# MR-Krabs: Zero-Hardcoded-Models Refactor

## Goal

Ship MR-Krabs with no baked-in model assumptions. The user's
principal agent walks them through defining every role and tier
during installation. Documentation shows *examples*, not *defaults*.

---

## 1. Config Schema (`~/.mrkrabs/config.yaml`)

Single source of truth. Every hardcoded value in the current codebase
derives from this file.

```yaml
version: "1.0"

# ── Providers ─────────────────────────────────────────
# Declared once, referenced by name in model definitions.
# Omitting `api_key_env` means no auth (local LM Studio).
providers:
  litellm:
    type: openai_compatible
    base_url: http://192.168.101.42:4000/v1
    api_key_env: LITELLM_MASTER_KEY
    timeout: 1800

  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    timeout: 300

  # Direct LM Studio backends (no proxy)
  lmstudio_21:
    type: openai_compatible
    base_url: http://192.168.101.21:1234/v1
    api_key: dummy
    timeout: 1800

# ── Models ────────────────────────────────────────────
# Every model the pipeline can call. `roles` is a list of
# tags used by workflows to select tiers. Multiple tags
# allowed (e.g., a model can be both planner and judge).
models:
  # Judge — quality gate for all workflows
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]

  # ── Planning stack ──
  l0-planner:
    provider: litellm
    model: mrk-planner-l0        # virtual endpoint on LiteLLM
    temperature: 0.0
    max_tokens: 16384
    roles: [planner]

  l1-planner:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]

  l2-planner:
    provider: openrouter
    model: anthropic/claude-sonnet-4.6
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]

  # ── Orchestrator ──
  orchestrator:
    provider: litellm
    model: mrk-orchestrator
    temperature: 0.0
    max_tokens: 32768
    roles: [orchestrator]

  # ── Coder stack ──
  l0-coder:
    provider: litellm
    model: mrk-coder-l0
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]
    tools: [file_write, file_read]

  l1-coder:
    provider: openrouter
    model: x-ai/grok-4.1-fast
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  l2-coder:
    provider: openrouter
    model: anthropic/claude-haiku-4.5
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]

  # ── Optional / budget builds ──
  l0-reviewer:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.3
    max_tokens: 4096
    roles: [reviewer]

  # ── Principal Agent (always present, never calls an LLM) ──
  principal:
    provider: none              # special — returns to caller
    roles: [principal]

# ── Workflows ─────────────────────────────────────────
# Each workflow defines an escalation chain. Tiers reference
# model keys above. The orchestrator walks the list in order,
# applying per-tier retry + judge evaluation at each step.
workflows:
  code:
    tiers: [l0-coder, l1-coder, l2-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge

  plan:
    tiers: [l0-planner, l1-planner, l2-planner, principal]
    max_retries_per_tier: 3
    judge_model: judge

  review:
    tiers: [l0-reviewer, principal]
    max_retries_per_tier: 2
    judge_model: judge

  # One-shot — no judge, no retries (used by FailNow)
  direct:
    tiers: []                   # caller must supply

# ── Tier Failure Actions ───────────────────────────────
# What happens when a tier exhausts all retries.
#   log_only           → log + continue to next tier
#   notify_and_escalate → notify + continue to next tier
#   notify_and_wait    → notify + block for human approval
# Omitted tiers default to "log_only".
tier_failure_actions:
  l0-coder: log_only
  l1-coder: notify_and_escalate
  l2-coder: notify_and_wait
  l0-planner: log_only
  l1-planner: notify_and_escalate
  l2-planner: notify_and_wait

# ── Budget (optional) ─────────────────────────────────
budget:
  daily_limit_usd: 10.00
  budget_awareness: true
  tier_thresholds:
    0.8: l2-coder              # budget > 80% remaining → allow L2
    0.5: l1-coder              # budget 50-80% → allow L1
    0.3: l0-coder              # budget < 30% → restrict to L0

# ── Profiles (optional) ───────────────────────────────
# Model-specific enrichments: known failure patterns and
# prepend prompts injected into the user prompt.
profiles:
  sushi-9b:
    known_failures:
      - trigger: "race condition"
        severity: warning
        feedback: "Sushi often misses concurrent access patterns"
      - trigger: "multi-file"
        severity: info
        feedback: "Sushi maxes out at ~400 lines; split large builds"
    prepend: "You are a compact 9B coder. Write concise, correct code."
```

### Field Defaults

Every scalar field has a sensible default so users only specify
what differs:

| Field | Default |
|---|---|
| `provider.timeout` | 300 |
| `model.temperature` | 0.7 |
| `model.max_tokens` | 4096 |
| `model.tools` | [] |
| `workflow.max_retries_per_tier` | 3 |
| `workflow.judge_model` | `"judge"` |
| `tier_failure_actions.<tier>` | `log_only` |
| `budget.daily_limit_usd` | 10.00 |
| `budget.budget_awareness` | false |

---

## 2. Code Changes (7 Hardcoded Sites → 0)

### 2.1 NEW: `src/core/config_loader.py`

```python
@dataclass
class ProviderConfig:
    name: str
    type: str                    # openai_compatible | none
    base_url: str
    api_key_env: str | None
    api_key: str | None
    timeout: int

@dataclass
class ModelConfig:
    key: str                     # "l0-coder", "judge", etc.
    provider: str
    model: str
    temperature: float
    max_tokens: int
    roles: list[str]
    tools: list[str]
    profile: str | None

@dataclass
class WorkflowConfig:
    name: str
    tiers: list[str]
    max_retries_per_tier: int
    judge_model: str

@dataclass
class MrKrabsConfig:
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    workflows: dict[str, WorkflowConfig]
    tier_failure_actions: dict[str, str]
    budget: BudgetConfig
    profiles: dict[str, ProfileConfig]

def load_config(path: str = "~/.mrkrabs/config.yaml") -> MrKrabsConfig:
    """Load and validate config. If no file exists, raise
    ConfigNotFoundError with a message pointing to the setup wizard."""
```

### 2.2 REPLACE: `src/core/model_config.py`

```python
# OLD: 170-line hardcoded MODELS dict
# NEW:
from src.core.config_loader import load_config

_config = None

def _get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config

def MODELS() -> dict:  # now a function, not a dict
    """Return MODELS dict in backward-compatible format."""
    cfg = _get_config()
    result = {}
    for key, m in cfg.models.items():
        provider = cfg.providers.get(m.provider)
        result[key] = {
            "provider": m.provider,
            "model": m.model,
            "base_url": provider.base_url if provider else "",
            "api_key_env": provider.api_key_env if provider else None,
            "temperature": m.temperature,
            "max_tokens": m.max_tokens,
            "tools": m.tools,
            "role": m.roles[0] if m.roles else "coder",
            "profile": m.profile,
        }
    return result
```

All existing `MODELS.get(tier, {})` calls change to `_get_config().models.get(tier)` 
or use the backward-compat `MODELS()` wrapper during migration.

### 2.3 MODIFY: `src/core/tier_manager.py`

| Current | New |
|---|---|
| `TIER_ORDER` class variable | Derived from config: filter models by role, sort by tier level |
| `TIER_ALIASES` dict | Removed — roles are explicit, no aliases needed |
| `get_tier()`, `get_next_tier()` | Query config, not `TIER_ORDER` |

### 2.4 MODIFY: `src/core/tier_config.py`

```python
# OLD: hardcoded TIER_FAILURE_DEFAULTS dict
# NEW: reads from config.tier_failure_actions

def get_tier_failure_action(tier: str) -> FailureAction:
    cfg = _get_config()
    action_str = cfg.tier_failure_actions.get(tier, "log_only")
    return FailureAction(action_str)
```

### 2.5 MODIFY: `src/core/orchestrator.py` (lines 760, 730)

```python
# OLD line 760:
tiers = tiers or ["L0-Coder", "L1-Coder", "L2-Coder", "Principal"]

# NEW:
cfg = _get_config()
default_workflow = cfg.workflows.get("code")
tiers = tiers or (default_workflow.tiers if default_workflow else [])
```

```python
# OLD line 730 (fail-now fallback):
available = [t for t in tiers or ["L0-Coder", ...] if t in MODELS]

# NEW:
cfg = _get_config()
all_tiers = [m.key for m in cfg.models.values() if "principal" not in m.roles]
available = [t for t in (tiers or all_tiers) if t in cfg.models]
```

### 2.6 MODIFY: `src/__init__.py` (line 84)

```python
# OLD:
preferred_order = ["L0-Coder", "L0-Planner", ...]

# NEW: pick cheapest available model (lowest tier number)
def _get_default_tier() -> str:
    cfg = _get_config()
    coders = [k for k, m in cfg.models.items() if "coder" in m.roles]
    return sorted(coders)[0] if coders else next(iter(cfg.models))
```

### 2.7 MODIFY: `src/core/analytics.py` (lines 203, 214, 223)

Replace hardcoded tier maps with dynamic derivation from config:

```python
def _get_tier_number(self, tier: str) -> int:
    cfg = _get_config()
    m = cfg.models.get(tier)
    if not m:
        return 0
    # Extract numeric tier from key: "l1-coder" → 1
    import re
    match = re.match(r'l(\d+)', tier.lower())
    return int(match.group(1)) if match else 0
```

### 2.8 MODIFY: `src/core/constants.py`

Remove: `LM_STUDIO_BASE_URL`, `OPENROUTER_BASE_URL`, `DEFAULT_JUDGE_MODEL`
These now come from config. Keep only true constants (timeout values, limits).

### 2.9 MODIFY: `src/core/judge.py`

The `Judge` class currently accepts a `model` parameter that looks up `MODELS["Judge"]`. Change to accept a `ModelConfig` object directly (provided by the orchestrator from its config).

---

## 3. Setup Wizard Flow

When MR-Krabs first runs and no `~/.mrkrabs/config.yaml` exists, the
user's principal agent walks them through:

```
┌─────────────────────────────────────────────────────────┐
│               MR-Krabs Configuration Wizard              │
│                                                         │
│  I'll help you define the models for each pipeline       │
│  role. For each one, you can:                            │
│    A) Use a LiteLLM virtual endpoint (if you have one)   │
│    B) Point to an OpenAI-compatible API directly          │
│    C) Skip this role (degrade gracefully)                │
│                                                         │
│  Let's start.                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1/8 — JUDGE (quality gate)                              │
│  Suggested: DeepSeek R1, Claude Sonnet, o4-mini          │
│  Required: Must be a reasoning-capable model             │
│  > _                                                    │
│                                                         │
│  2/8 — L0-CODER (cheapest, tried first)                  │
│  Suggested: 30B+ MoE local, Grok 4.1 Fast               │
│  > _                                                    │
│                                                         │
│  3/8 — L1-CODER (fallback, moderate cost)                │
│  Suggested: Gemini 2.5 Flash, Claude Haiku 4.5           │
│  > _                                                    │
│                                                         │
│  4/8 — L2-CODER (last resort before principal)           │
│  Suggested: Claude Sonnet 4.6, GPT-5                     │
│  > _                                                    │
│                                                         │
│  5/8 — L0-PLANNER (task decomposition)                   │
│  Suggested: Gemini 2.5 Pro, 30B+ MoE                     │
│  > _                                                    │
│                                                         │
│  6/8 — L1-PLANNER (fallback planner)                     │
│  Suggested: Gemini 2.5 Flash                             │
│  > _                                                    │
│                                                         │
│  7/8 — ORCHESTRATOR (task routing & coordination)        │
│  Suggested: 30B+ MoE local, Claude Sonnet                │
│  > _                                                    │
│                                                         │
│  8/8 — ESCALATION PATHS                                  │
│  Settings loaded from your role definitions.             │
│  Review:                                                 │
│    code:   l0-coder → l1-coder → l2-coder → principal    │
│    plan:   l0-planner → l1-planner → principal           │
│    review: l0-reviewer → principal                       │
│  > [accept] / [edit]                                     │
│                                                         │
│  ✓ Config written to ~/.mrkrabs/config.yaml              │
│  ✓ 8 roles defined, 3 workflows configured              │
│  Run 'mrkrabs doctor' to validate connectivity.          │
└─────────────────────────────────────────────────────────┘
```

The wizard doesn't need a CLI — the principal agent can ask questions
directly:

```
H: "For the Judge, do you want DeepSeek R1 via OpenRouter, 
    or Claude Sonnet 4.6, or something else?"
U: "Claude Sonnet 4.6 via LiteLLM endpoint mrk-judge"
H: [writes to config.yaml, moves to next role]
```

Prompt format for each role:

```
ROLE: <name> (<description>)
WHAT IT DOES: <one-liner>
SUGGESTED MODELS: <3-4 options at different price points>
REQUIRED?: <yes/no — if yes, pipeline can't run without it>
YOUR CHOICE (provider model): _____________
```

---

## 4. Migration Path

### Phase A: Non-breaking infra (backward compat)
1. Write `config_loader.py` — reads config OR auto-generates from
   current hardcoded `MODELS` dict
2. Write `MODELS()` backward-compat wrapper
3. All existing code keeps working unchanged

### Phase B: Switch callers to config
4. Replace `MODELS.get(tier)` calls with `config.models.get(tier)` 
   in orchestrator, judge, tier_manager, tier_config, analytics
5. Add `WorkflowRegistry` to replace hardcoded defaults (line 760 etc.)
6. All existing tests pass with auto-generated config from legacy MODELS

### Phase C: Zero-hardcoded mode
7. Replace `MODELS` dict with empty `{}` → `model_config.py` produces
   `ConfigNotFoundError` if no config file exists
8. Add setup wizard prompt logic (principal agent driven)
9. Update all docs to show examples, not defaults
10. Add `mrkrabs doctor` command to validate config connectivity

### Phase D: Remove legacy
11. Delete `MODELS()` backward-compat wrapper
12. Delete `TIER_ORDER`, `TIER_ALIASES` from tier_manager
13. All code reads exclusively from `MrKrabsConfig`

---

## 5. Files Summary

| File | Action |
|---|---|
| `src/core/config_loader.py` | **NEW** — reads/validates YAML |
| `src/core/workflow_registry.py` | **NEW** — escalation chain lookup |
| `src/core/model_config.py` | **REWRITE** — loads from config, not hardcoded dict |
| `src/core/tier_manager.py` | **MODIFY** — derive from config, not TIER_ORDER |
| `src/core/tier_config.py` | **MODIFY** — read failure actions from config |
| `src/core/orchestrator.py` | **MODIFY** — lines 730, 760, config-driven defaults |
| `src/core/judge.py` | **MODIFY** — accept ModelConfig, not MODELS lookup |
| `src/core/constants.py` | **MODIFY** — remove URL/model defaults |
| `src/core/analytics.py` | **MODIFY** — dynamic tier maps |
| `src/__init__.py` | **MODIFY** — derive default tier from config |
| `src/cli/setup.py` | **NEW** — `mrkrabs setup` wizard entry point |
| `tests/fixtures/sample_config.yaml` | **NEW** — minimal test config |
| `docs/MODEL_CONFIG.md` | **NEW** — examples, not defaults |

---

*Plan written 2026-06-04. Ready for implementation on approval.*
