# MR-Krabs Architecture

**Config-driven, judge-gated, multi-tier coding agent.**

## Recommended Infrastructure

**MR-Krabs is designed to work with [llama.cpp](https://github.com/ggerganov/llama.cpp).**
llama.cpp is the only recommended model server — it handles tool-call formats,
stop-token behavior, and reasoning-model content extraction correctly. We
strongly advise against LM Studio (known jinja template injection bugs),
Ollama (tool-call inconsistencies), and vLLM (stop-token behaviour differences).

## Pipeline

```
Tier Loop: L0 → L1 → L2 → Principal
  ┌─ Circuit Breaker gate → FailUp check
  │
  │  Retry Loop (per tier):
  │    Context compression → OpenCode subprocess → Tool execution
  │         │                                              │
  │         │                                    ┌─ Read files from disk
  │         │                                    │
  │         ▼                                    ▼
  │    ┌──────────────── Judge evaluation ────────────────┐
  │    │  (structured spec injected if context['spec'])    │
  │    │  (known failures checked per model profile)       │
  │    └──────────┬────────────────────────┬──────────────┘
  │               │                        │
  │          Accepted                 Rejected
  │               │                        │
  │     Checkpoint written          Checkpoint written
  │     Clear checkpoint            Coaching feedback
  │     return SUCCESS              Fix-mode prompt
  │          ↑                              │
  │          └── Provisional accept ────────┘ (free revision)
  │
  │  Retries exhausted → FailureAction → escalate
  │  Consecutive 3x same error → skip remaining → Principal
  │
  Principal reached → return escalation_context to caller
  Post-pipeline: self-improvement hook (opt-in)
```

### New Pipeline Features (Jun 2026)

| Feature | What It Does |
|---------|-------------|
| **Context compression** | Summarizes old judge feedback, compresses accumulated file lists >5 files. Emits `context_fill_ratio` to PipelineMonitor |
| **Checkpoint/resume** | Saves state after every tier verdict. Resume via `resume_from_checkpoint=True` to skip completed tiers |
| **Fix-mode prompt** | Retries with judge feedback use a dedicated `fix-system-prompt.md` — "FIX THE ISSUES. CHANGE AS LITTLE AS POSSIBLE." |
| **Structured task contracts** | Optional `context['spec'] = {success_criteria, constraints, anti_patterns}` injected into judge prompt |
| **Consecutive error threshold** | 3 consecutive same-category failures → skip remaining tiers → Principal directly |
| **Self-improvement loop** | Opt-in (`MRKRABS_SELF_IMPROVE=1`). Reads verdict data, discovers failure patterns, auto-updates `model_profiles.py` |

## Coder Backend

The default coder sub-agent is **OpenCode CLI** (`opencode run`). Each coder tier
spawns an OpenCode process that writes files directly to disk, then the orchestrator
reads them back for Judge evaluation. OpenCode is the recommended backend because it:

- Works reliably with llama.cpp (no jinja template issues)
- Handles multi-file tasks with native tool use (write, bash, read, edit)
- Produces verifiable output — files on disk, not parsed from model text

**PI Coding Agent** is available as a fallback. Configure `pi_models` in your config
to use PI for specific tiers. When a tier has both `opencode_models` and `pi_models`
entries, OpenCode takes priority.

```yaml
# Default: OpenCode for all coder tiers
opencode_models:
  l0-coder: llama_cpp_23/ornith-1.0-35b
  l1-coder: openrouter/deepseek/deepseek-v4-flash
  l2-coder: openrouter/xiaomi/mimo-v2.5

opencode_timeouts:
  l0-coder: 2400
  l1-coder: 1200
  l2-coder: 1200

# Fallback: PI for specific tiers
pi_models:
  l0-coder: litellm/mrk-coder-l0
```

Execution: spawns OpenCode → writes files to `project_root` → orchestrator reads
files → feeds contents to Judge.

When neither OpenCode nor PI is configured, falls back to raw LLM via ProviderRouter.

## Context Compression (Pillar 2)

The context compressor (`src/core/context_compressor.py`) runs on every retry
to prevent context window overflow:

1. **Task spec + system prompt** — always preserved verbatim
2. **Accumulated files** — compressed to summary when >5 files
3. **Judge feedback history** — older critiques summarized, most recent kept verbatim
4. **Model profile prepend** — preserved (small, high-value)

PipelineMonitor receives `context_fill_ratio` after each compression — warnings
emitted at >80% fill.

## Tier Hierarchy

**Example deployment.** Configure your own in `~/.mrkrabs/config.yaml`.
See [MODEL_CONFIG.md](MODEL_CONFIG.md).

| Tier | Example | Runtime | Cost | Role |
|------|---------|---------|------|------|
| L0-Coder | 30B MoE on llama.cpp | OpenCode on local GPU | Free | ~75% success |
| L1-Coder | Fast cloud model | OpenCode via OpenRouter | Cloud | First escalation |
| L2-Coder | Premium cloud model | OpenCode via OpenRouter | Cloud | Second escalation |
| Principal | — | Calling agent | Your sub | Final fallback |

## Judge System

| Property | Value |
|----------|-------|
| Class | Reasoning model recommended |
| Temperature | 0.1 |
| Threshold | 0.7 (configurable) |
| Rubric | Anchored 0.0–1.0 |
| Structured spec | Optional `spec` dict with `success_criteria`, `constraints`, `anti_patterns` |
| Provisional accept | Scores 0.75–0.85 get free revision without consuming retry budget |

Coaching reply structure (on rejection): what was done well → what's wrong → why → how to fix → verify.

## Principal Agent

Returns structured result with full escalation context including best output and file contents so the calling agent can continue.

## Checkpointing

After every tier verdict (accept or reject), the orchestrator writes a checkpoint
to `docs/workflow/escalations/<task_id>_checkpoint.json`. Checkpoints contain:

- `escalation_path` — tiers completed so far
- `accumulated_files` — files on disk from completed tiers
- `retries_per_tier` — attempt counts per tier
- `best_output` — highest-scoring output across all attempts
- `cost_summary` — accumulated spend

Pass `resume_from_checkpoint=True` to `execute_with_judge()` to restore state
and skip already-completed tiers. Successful runs clear the checkpoint.

## Self-Improvement Loop

Opt-in via `MRKRABS_SELF_IMPROVE=1`. The SelfImprover (`src/core/self_improver.py`)
runs post-pipeline:

1. Reads verdict data from `~/.mrkrabs/debug/`
2. Groups rejected critiques by model/tier
3. Discovers recurring failure patterns (≥2 occurrences, ≥40% frequency)
4. Injects `KnownFailure` entries into `src/core/model_profiles.py`

Discovered patterns are marked `[AUTO-DISCOVERED]` and never overwrite manual entries.

## Configuration-Driven

No hardcoded models or tiers. `~/.mrkrabs/config.yaml` defines everything.

See [MODEL_CONFIG.md](MODEL_CONFIG.md) for full reference.

## Key Files

| File | Purpose |
|------|---------|
| `src/core/orchestrator.py` | Main pipeline — `execute_with_judge()`, tier/retry loop, checkpointing |
| `src/core/context_compressor.py` | Prompt compression — summarizes feedback, compresses file lists |
| `src/core/self_improver.py` | Post-pipeline pattern discovery → model profile updates |
| `src/core/judge.py` | Judge class, verdict evaluation, coaching reply prompt |
| `src/core/judge_criteria.py` | Criteria definitions, task type detection, coder task size limits |
| `src/core/model_config.py` | Model configuration loading (zero hardcoded models) |
| `src/core/model_profiles.py` | Per-model capability profiles + known failure patterns |
| `src/core/cost.py` | CostTracker — observer-only spend tracking |
| `src/core/circuit_breaker.py` | Per-model circuit breaker registry |
| `src/core/pipeline_monitor.py` | Pipeline health: anomalies, context fill, truncation detection |
| `src/core/task_splitter.py` | Deterministic file reference parser → multi-pass execution |
| `src/core/notify.py` | Pluggable notification backends (Telegram, Mesh) |
| `src/core/failure_action.py` | LOG_ONLY / NOTIFY_AND_ESCALATE / NOTIFY_AND_WAIT |
| `src/core/fail_now.py` | FailNow/FailUp emergency signals |
| `src/core/human_gate.py` | Human-in-the-loop confirmation for NOTIFY_AND_WAIT |
| `docs/workflow/templates/` | System prompt templates: code, plan, fix (standard + PI variants) |
