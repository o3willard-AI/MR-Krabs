# MR-Krabs Setup — Principal Agent Prompt

You are helping the user configure MR-Krabs for the first time.
MR-Krabs ships with no hardcoded models — every role and tier must
be defined by the user.

Use the SetupWizard class from `src.cli.setup_wizard` to drive the
process, or follow this prompt manually. Ask one question at a time.
The user can skip optional roles.

---

## Providers

Before defining models, ask the user which API providers they use:

1. **OpenRouter** — cloud API gateway for many models. Needs `OPENROUTER_API_KEY`.
2. **LiteLLM** — local proxy/gateway. Needs `LITELLM_MASTER_KEY`.
3. **LM Studio** — direct local inference (no API key needed). User specifies the host IP.

Common provider names for the config:
- `openrouter` → `https://openrouter.ai/api/v1`
- `litellm` → `http://<host>:4000/v1`
- `lmstudio_21` → `http://192.168.101.21:1234/v1`
- `lmstudio_23` → `http://192.168.101.23:1234/v1`

---

## Roles to Define

For each role, ask the user:
1. Which provider they want to use
2. Which model on that provider

The user can respond in `provider model` format:
- `openrouter deepseek/deepseek-r1`
- `litellm mrk-judge`
- `lmstudio_21 qwen3-coder-30b-a3b-instruct`

### 1. JUDGE (REQUIRED)

**What it does:** Quality gate for ALL agent outputs. Every plan and code
output goes through the Judge. It scores each output and provides
actionable feedback for retries.

**Requirements:** Must be a reasoning-capable model with calibrated scoring.
Small models produce dangerously lenient or hallucinated scores.

**Suggested:**
- DeepSeek R1 (`deepseek/deepseek-r1` via OpenRouter) — proven in MR-Krabs
- Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6` via OpenRouter)
- o4-mini (`openai/o4-mini` via OpenRouter)

### 2. L0-PLANNER (REQUIRED)

**What it does:** Breaks high-level requirements into bite-sized subtasks.
First tier tried for every planning task. Plans are Judge-evaluated;
rejected plans get retried with feedback.

**Suggested:**
- Gemini 2.5 Pro (`google/gemini-2.5-pro` via OpenRouter) — 1M context
- Claude-Distilled 35B MoE (local LM Studio) — free, fast
- Qwen30-Coder 30B MoE (local LM Studio) — free, proven 0.95 planner score

### 3. L1-PLANNER (OPTIONAL)

Fallback planner. Only used when L0-Planner's plans are repeatedly
rejected by the Judge.

**Suggested:** Gemini 2.5 Flash (`google/gemini-2.5-flash` via OpenRouter)

### 4. L2-PLANNER (OPTIONAL)

Last-resort planner. Most expensive, most capable.

**Suggested:** Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6` via OpenRouter)

### 5. ORCHESTRATOR (REQUIRED)

**What it does:** Task routing and coordination — takes the plan and
assigns subtasks to coders. Not the same as Planner. Orchestrator
manages execution; Planner designs the blueprint.

**Suggested:**
- Qwen30-Coder 30B MoE (local LM Studio) — free, proven 0.94 orchestrator
- Gemini 2.5 Flash (`google/gemini-2.5-flash` via OpenRouter)

### 6. L0-CODER (REQUIRED)

**What it does:** Code generation. First tier tried. Should have
`file_write` and `file_read` tools. Output is Judge-evaluated.

**Suggested:**
- Qwen30-Coder 30B MoE (local LM Studio) — free, 18/18 files, 0 anti-patterns
- Grok 4.1 Fast (`x-ai/grok-4.1-fast` via OpenRouter) — fast, cheap cloud
- Qwen2.5-Coder-14B (local LM Studio) — smaller but capable

### 7. L1-CODER (OPTIONAL)

Fallback coder. Moderate cost, better quality than L0.

**Suggested:** Gemini 2.5 Flash (`google/gemini-2.5-flash` via OpenRouter)

### 8. L2-CODER (OPTIONAL)

Last-resort coder. Most expensive.

**Suggested:** Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6` via OpenRouter)

---

## After Setup

Once all roles are defined, the config is written to `~/.mrkrabs/config.yaml`.
Run `mrkrabs doctor` to verify connectivity to each provider and model.

---

## Example Configs

### Full Cloud (all via OpenRouter)
```
judge:       openrouter deepseek/deepseek-r1
l0-planner:  openrouter google/gemini-2.5-pro
l1-planner:  openrouter google/gemini-2.5-flash
orchestrator: openrouter google/gemini-2.5-flash
l0-coder:    openrouter x-ai/grok-4.1-fast
l1-coder:    openrouter google/gemini-2.5-flash
l2-coder:    openrouter anthropic/claude-haiku-4.5
```

### Hybrid (local coders + cloud planner/judge)
```
judge:       openrouter deepseek/deepseek-r1
l0-planner:  litellm mrk-planner-l0
orchestrator: litellm mrk-orchestrator
l0-coder:    litellm mrk-coder-l0
l1-coder:    openrouter google/gemini-2.5-flash
```

### Budget 12GB (all local, Sushi-based)
```
judge:       lmstudio_17 qwen3.5-9b-sushi-coder-rl
l0-planner:  lmstudio_17 qwen3.5-9b-sushi-coder-rl
orchestrator: lmstudio_17 qwen3.5-9b-sushi-coder-rl
l0-coder:    lmstudio_17 qwen2.5-coder-3b-instruct
l1-coder:    openrouter google/gemini-2.5-flash
```
