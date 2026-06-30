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

## OpenCode not found

**Symptom:** `FileNotFoundError: opencode` or `OpenCode CLI not found`.

**Fix:** Install OpenCode globally:
```bash
npm install -g opencode-ai@latest
```
Verify with:
```bash
opencode --version
opencode auth list
```

## PI not found (fallback backend)

**Symptom:** `FileNotFoundError: pi` or `PI coding agent not found` when
a tier is configured with `pi_models`.

**Fix:** Either install PI (`npm install -g @anthropic-ai/pi-coding-agent`)
or switch the tier to use OpenCode by configuring `opencode_models` instead.

## API key missing

**Symptom:** `ValueError: API key not found` or 401 responses from providers.

**Fix:** Set the environment variable referenced in your config's `api_key_env`:
```bash
export OPENROUTER_API_KEY=sk-or-...
```
Run `python -m src.validators.startup` to verify connectivity.

## llama.cpp server unreachable

**Symptom:** Connection refused, timeout, or DNS errors when contacting
the llama.cpp server's `base_url`.

**Fix:**
1. Verify llama.cpp is running: `curl http://192.168.101.23:8080/v1/models`
2. Check the `base_url` in `~/.mrkrabs/config.yaml` matches the server
3. Verify the model is loaded: `curl http://192.168.101.23:8080/v1/models | jq '.data[].id'`
4. Check the `timeout` value isn't too low (1800 is safe for local models)
5. If using a systemd service: `systemctl status llama-server`

## Templates validation fails

**Symptom:** `python -m src.validators.templates` reports invalid templates.

**Fix:** Open each reported file and ensure it follows these rules:
- First line must be `# ROLE: <role name>`
- File must be at least 50 characters
- Location: `docs/workflow/templates/`

## OpenCode output is empty or truncated

**Symptom:** Judge receives empty output, or the task fails with no files written.

**Likely cause:** The task is too large for the model's context window, or the
model exhausted its token budget on chain-of-thought reasoning before producing
visible content.

**Fix:**
- Enable prompt flow debugging: `MRKRABS_PROMPT_FLOW_DEBUG=1`
- Check `~/.mrkrabs/debug/<task_id>/` for the raw prompt and response
- Break the task into smaller pieces (≤20 files per pass)
- Raise `max_tokens` for the coder tier in config.yaml
- For reasoning models (Claude-Distilled), use at least 200 `max_tokens`
- Verify OpenCode is configured correctly:
  ```bash
  opencode run --model <provider>/<model> 'Write a file /tmp/oc-smoke-test.txt containing exactly: TOOL_OK'
  cat /tmp/oc-smoke-test.txt
  ```

## Judge rejects everything

**Symptom:** All tiers exhausted, every output scored below threshold.

**Likely causes (check in order):**
1. **Wrong model for judging** — small models produce unreliable scores.
   Use a reasoning model (see [JUDGE.md](JUDGE.md)).
2. **Threshold too high** — default is 0.7. Try 0.6 for prototyping.
3. **Criteria too strict** — review criteria in [judge_criteria.py](../src/core/judge_criteria.py).
4. **Actual bug in output** — check `MRKRABS_PROMPT_FLOW_DEBUG=1` dumps and read
   the coaching reply for specific file/line issues.

## Context overflow — compression active

**Symptom:** The orchestrator prints `⚠️ Context fill: >80% — compression active`
during retries. Older judge feedback is being summarized rather than passed
verbatim.

**This is expected behavior, not a failure.** When multiple retries accumulate
feedback within a tier, the context compressor (Article Pillar 2) activates:

- Older judge critiques are summarized into one-line entries
- Accumulated file lists >5 files are compressed to a count + top-N
- The most recent judge critique is always preserved verbatim
- Task spec and system prompt are never compressed

**To reduce compression:** Use smaller task specs (<3KB) or fewer files per pass.
If you see the warning consistently, the pipeline is still working correctly —
the compressor is doing its job.

**To inspect what was compressed:** Enable prompt flow debug:
```bash
MRKRABS_PROMPT_FLOW_DEBUG=1 python -m src.core.orchestrator --task "..."
# Look at ~/.mrkrabs/debug/<task_id>/ for the compressed prompt
```

## Pipeline killed — resume from checkpoint

**Symptom:** A long-running pipeline was killed mid-escalation (SIGTERM, session
end, manual stop). All progress appears lost.

**Fix:** Resume from the checkpoint that was written after the last completed tier:
```python
result = orch.execute_with_judge(
    task_id="same-task-id-as-before",
    context={"task_spec": "..."},
    tiers=["l0-coder", "l1-coder", "l2-coder", "principal"],
    max_retries_per_tier=3,
    resume_from_checkpoint=True,
)
```

Checkpoints are written to `docs/workflow/escalations/<task_id>_checkpoint.json`
after every tier verdict. They contain:

- `escalation_path` — tiers already completed (skipped on resume)
- `accumulated_files` — files on disk from completed tiers (restored)
- `retries_per_tier` — attempt counts per tier (restored)
- `best_output` — highest-scoring output so far (restored)

**To inspect a checkpoint:**
```bash
cat docs/workflow/escalations/<task_id>_checkpoint.json | python -m json.tool
```

**To reset and start fresh:** Delete the checkpoint file:
```bash
rm docs/workflow/escalations/<task_id>_checkpoint.json
```

## OpenCode writes files to wrong directory

**Symptom:** Files appear in the MR-Krabs repo instead of the target project.

**Likely cause:** OpenCode resolves its working directory from where it was
invoked. The orchestrator must pass `project_root` to `execute_with_judge()`.

**Fix:** Always pass `project_root` when calling the orchestrator:
```python
result = orch.execute_with_judge(
    task_id="my-task",
    context={"task_spec": "..."},
    tiers=["l0-coder"],
    project_root="/path/to/target/project",  # ← required
)
```

## Planner → OpenCode → Judge: the feedback loop

The three most common "pipeline broken" failures are not bugs — they're
mismatches between what the planner asks, what OpenCode produces, and what the
judge expects. These three components form a chain, and most failures
trace to one link expecting something the previous link never promised.

### The planner's job: give OpenCode a spec it can actually execute

OpenCode is not an architect. It receives a task spec and writes code. If the
spec is vague ("add authentication"), verbose (16KB of architecture
discussion), or asks for too much (30+ files in one pass), OpenCode will produce
garbage or truncate.

**A good OpenCode spec is:**
- **Under 8 KB.** OpenCode has a finite context window. Verbose plans cause
  instructions to scroll out of reach.
- **File-by-file.** Name each file, describe its purpose, list what it
  imports and exports.
- **Self-contained.** Don't reference conversations OpenCode wasn't part of.
- **Bite-sized.** ≤20 files per pass. Larger tasks go through the
  multi-pass splitter.

**Symptom of bad planner output:** OpenCode writes files that don't match the
task, skips files entirely, or produces a plan that truncates mid-sentence
at ~16K tokens. The planner model may need a higher `max_tokens` or a
different model. Non-reasoning models work better for planning —
reasoning models often exhaust their token budget on chain-of-thought
before producing content.

### OpenCode's natural behavior: multiple files, partial output, salvage

On real tasks, OpenCode writes 5-15 files per pass. This is normal. On larger
tasks, OpenCode will often **truncate** — it writes 7 of 10 files before
hitting its output token limit and the response cuts off.

**This is expected, not a failure.** The pipeline's partial salvage
mechanism detects files already on disk even when OpenCode's output didn't
complete. A pass that wrote 7/10 files should be scored on those 7, and
the remaining 3 should be retried — not the whole pass discarded.

**Symptom of misconfiguration:** OpenCode output is discarded wholesale because
it lacks a clean DONE marker. The files sit orphaned on disk while the
orchestrator escalates to L1 → L2. Check that `opencode_timeouts` in config.yaml
are generous enough (2400s for local L0, 1200s for cloud).

### The judge's job: score what OpenCode actually produces

The judge evaluates files on disk, not OpenCode's raw transcript. OpenCode output
includes tool-call traces, JSON events, and process chatter — the judge
never sees any of this. It sees completed file contents.

**Judge calibration for OpenCode output:**
- OpenCode writes production-style code: docstrings, type hints, tests. This is
  normal — don't penalize for verbosity.
- OpenCode may write files in a different order than the spec listed. Judge by
  file content, not creation order.
- On multi-file tasks, OpenCode occasionally leaves minor inconsistencies
  between files (import paths, function signatures). These are in the
  0.6-0.8 range — acceptable at the default 0.7 threshold.
- If the judge consistently scores OpenCode output at 0.5-0.6, the threshold is
  too high for the coder model. Lower it to 0.6, or upgrade the coder.

**Symptom of judge misconfiguration:** Every OpenCode output scores 0.4-0.5,
L0 always escalates, cloud costs spike. The judge and coder are
mismatched — either lower the threshold or use a judge model that's
calibrated to the coder's typical quality level.

### Tuning the loop end-to-end

The fastest way to diagnose a loop problem is to run one task with
`MRKRABS_PROMPT_FLOW_DEBUG=1` and inspect all three artifacts:

```
~/.mrkrabs/debug/<task_id>/
├── planner-prompt.txt    # What the planner received
├── planner-output.txt    # The spec it produced → fed to OpenCode
├── l0-coder-prompt.txt   # OpenCode's system prompt + planner spec
├── l0-coder-output.txt   # OpenCode's raw transcript
├── judge-prompt.txt      # File contents fed to judge
└── judge-output.json     # Score + coaching reply
```

**Read them in order.** The failure is usually at a handoff:
- `planner-output.txt` is 14KB and truncated → planner model needs fixing
- `l0-coder-output.txt` wrote files but the spec was ambiguous → planner
  needs to be more specific
- `judge-output.json` scored 0.3 but the files look correct → judge model
  is too small, or threshold needs recalibration

## LM Studio / Ollama / vLLM issues

**We do not recommend non-llama.cpp backends.** If you're using LM Studio,
Ollama, or vLLM and encountering issues:

- **LM Studio:** Known jinja template injection bug (`Unknown StringValue filter: safe`)
  with OpenCode and PI. Non-community models fail with `Cannot call something that is
  not a function: got UndefinedValue`. **Fix:** Migrate to llama.cpp.
- **Ollama:** Tool-call format incompatibilities with some models. Stop-token
  behavior inconsistent across model versions. **Fix:** Migrate to llama.cpp.
- **vLLM:** Ignores custom stop tokens in some configurations. Reasoning model
  content extraction differs from llama.cpp. **Fix:** Migrate to llama.cpp.

See the [OpenCode skill references](https://github.com/o3willard-AI/MR-Krabs)
for the full LM Studio jinja workaround (legacy, not recommended).

## Still stuck?

Run the full validation suite:
```bash
python -m src.validators.templates   # template format
python -m src.validators.startup     # config + API connectivity
python -m src.validators.models      # model provisioning
python -m pytest tests/ -q           # unit/integration tests
```

Open an issue with the output of all four commands.
