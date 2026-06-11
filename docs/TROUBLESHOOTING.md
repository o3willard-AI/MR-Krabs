# Troubleshooting

Common failure modes and how to fix them.

## Config not found

**Symptom:** `ConfigNotFoundError` on startup.

```
No model configuration found.

MR-Krabs does not ship with hardcoded models. Your principal
agent should walk you through defining each pipeline role.

Create ~/.mrkrabs/config.yaml, then run 'mrkrabs doctor' to
validate connectivity.
```

**Fix:** Create `~/.mrkrabs/config.yaml`. Copy an example from
[docs/MODEL_CONFIG.md](MODEL_CONFIG.md) and adapt it to your setup.

## PI not found

**Symptom:** `FileNotFoundError: pi` or `PI coding agent not found`.

**Fix:** Install PI globally:
```bash
npm install -g @anthropic-ai/pi-coding-agent
```
Or set `PI_PATH` to the local install:
```bash
export PI_PATH=/path/to/node_modules/.bin/pi
```

## API key missing

**Symptom:** `ValueError: API key not found` or 401 responses from providers.

**Fix:** Set the environment variable referenced in your config's `api_key_env`:
```bash
export LITELLM_MASTER_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...
```
Run `python -m src.validators.startup` to verify connectivity.

## Provider unreachable

**Symptom:** Connection refused, timeout, or DNS errors when contacting the
provider's `base_url`.

**Fix:**
1. Verify the provider is running: `curl http://192.168.101.42:4000/v1/models`
2. Check the `base_url` in `~/.mrkrabs/config.yaml` is correct
3. Verify network connectivity and firewall rules
4. Check the `timeout` value isn't too low (1800 is safe for local models)

## Templates validation fails

**Symptom:** `python -m src.validators.templates` reports invalid templates.

**Fix:** Open each reported file and ensure it follows these rules:
- First line must be `# ROLE: <role name>`
- File must be at least 50 characters
- Location: `docs/workflow/templates/`

## PI output is empty or truncated

**Symptom:** Judge receives empty output, or the task fails with no files written.

**Likely cause:** The task is too large for a single PI call. The model's output
token limit was reached mid-response.

**Fix:**
- Enable prompt flow debugging: `MRKRABS_PROMPT_FLOW_DEBUG=1`
- Check `~/.mrkrabs/debug/<task_id>/` for the raw prompt and response
- Break the task into smaller pieces (≤20 files per pass)
- Raise `max_tokens` for the coder tier in config.yaml

## Judge rejects everything

**Symptom:** All tiers exhausted, every output scored below threshold.

**Likely causes (check in order):**
1. **Wrong model for judging** — small models produce unreliable scores.
   Use a reasoning model (see [JUDGE.md](JUDGE.md)).
2. **Threshold too high** — default is 0.7. Try 0.6 for prototyping.
3. **Criteria too strict** — review criteria in [judge_criteria.py](../src/core/judge_criteria.py).
4. **Actual bug in output** — check `MRKRABS_PROMPT_FLOW_DEBUG=1` dumps and read
   the coaching reply for specific file/line issues.

## Planner → PI → Judge: the feedback loop

The three most common "pipeline broken" failures are not bugs — they're
mismatches between what the planner asks, what PI produces, and what the
judge expects. These three components form a chain, and most failures
trace to one link expecting something the previous link never promised.

### The planner's job: give PI a spec it can actually execute

PI is not an architect. It receives a task spec and writes code. If the
spec is vague ("add authentication"), verbose (16KB of architecture
discussion), or asks for too much (30+ files in one pass), PI will produce
garbage or truncate.

**A good PI spec is:**
- **Under 8 KB.** PI has a finite context window. Verbose plans cause
  instructions to scroll out of reach.
- **File-by-file.** Name each file, describe its purpose, list what it
  imports and exports.
- **Self-contained.** Don't reference conversations PI wasn't part of.
- **Bite-sized.** ≤20 files per pass. Larger tasks go through the
  multi-pass splitter.

**Symptom of bad planner output:** PI writes files that don't match the
task, skips files entirely, or produces a plan that truncates mid-sentence
at ~16K tokens. The planner model may need a higher `max_tokens` or a
different model. Non-reasoning models work better for planning —
reasoning models often exhaust their token budget on chain-of-thought
before producing content.

### PI's natural behavior: multiple files, partial output, salvage

On real tasks, PI writes 5-15 files per pass. This is normal. On larger
tasks, PI will often **truncate** — it writes 7 of 10 files before
hitting its output token limit and the response cuts off.

**This is expected, not a failure.** The pipeline's partial salvage
mechanism detects files already on disk even when PI's output didn't
complete. A pass that wrote 7/10 files should be scored on those 7, and
the remaining 3 should be retried — not the whole pass discarded.

**Symptom of misconfiguration:** PI output is discarded wholesale because
it lacks a clean DONE marker. The files sit orphaned on disk while the
orchestrator escalates to L1 → L2. Check that `pi_timeouts` in config.yaml
are generous enough (2400s for local L0, 1200s for cloud).

### The judge's job: score what PI actually produces

The judge evaluates files on disk, not PI's raw transcript. PI output
includes tool-call traces, JSON events, and process chatter — the judge
never sees any of this. It sees completed file contents.

**Judge calibration for PI output:**
- PI writes production-style code: docstrings, type hints, tests. This is
  normal — don't penalize for verbosity.
- PI may write files in a different order than the spec listed. Judge by
  file content, not creation order.
- On multi-file tasks, PI occasionally leaves minor inconsistencies
  between files (import paths, function signatures). These are in the
  0.6-0.8 range — acceptable at the default 0.7 threshold.
- If the judge consistently scores PI output at 0.5-0.6, the threshold is
  too high for the coder model. Lower it to 0.6, or upgrade the coder.

**Symptom of judge misconfiguration:** Every PI output scores 0.4-0.5,
L0 always escalates, cloud costs spike. The judge and coder are
mismatched — either lower the threshold or use a judge model that's
calibrated to the coder's typical quality level.

### Tuning the loop end-to-end

The fastest way to diagnose a loop problem is to run one task with
`MRKRABS_PROMPT_FLOW_DEBUG=1` and inspect all three artifacts:

```
~/.mrkrabs/debug/<task_id>/
├── planner-prompt.txt    # What the planner received
├── planner-output.txt    # The spec it produced → fed to PI
├── l0-coder-prompt.txt   # PI's system prompt + planner spec
├── l0-coder-output.txt   # PI's raw transcript
├── judge-prompt.txt      # File contents fed to judge
└── judge-output.json     # Score + coaching reply
```

**Read them in order.** The failure is usually at a handoff:
- `planner-output.txt` is 14KB and truncated → planner model needs fixing
- `l0-coder-output.txt` wrote files but the spec was ambiguous → planner
  needs to be more specific
- `judge-output.json` scored 0.3 but the files look correct → judge model
  is too small, or threshold needs recalibration

## Still stuck?

Run the full validation suite:
```bash
python -m src.validators.templates   # template format
python -m src.validators.startup     # config + API connectivity
python -m src.validators.models      # model provisioning
python -m pytest tests/ -q           # unit/integration tests
```

Open an issue with the output of all four commands.
