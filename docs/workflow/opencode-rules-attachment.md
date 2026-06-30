# OpenCode Rules Attachment System

## What This Is

Every time MR-Krabs delegates a coding task to OpenCode, it attaches a
file of domain-specific coding standards via `opencode run -f <rules.md>`.
This file persists through OpenCode's auto-compaction, unlike rules
embedded in the user prompt, which get summarized away after 2-3
compaction rounds.

## Why It Exists

### The Problem

OpenCode's built-in system prompt (`default.txt`) tells the model:

> "DO NOT ADD ANY COMMENTS unless asked"
> "You MUST answer concisely with fewer than 4 lines of text"
> "Minimize output tokens as much as possible"

Meanwhile, PI's system prompt (`code-pi-system-prompt.md`) tells the model:

> "Complete implementations. No stubs, no TODO, no pass."
> "Handle edge cases, validate inputs, add docstrings."
> "Production quality."

This creates a **quality differential** when the same model (Ornith-1.0-35B)
is called through different agents:

| | PI | OpenCode |
|---|---|---|
| System prompt tone | "Production quality" | "Minimize output" |
| shlex.quote() calls | ~15 (thorough) | 3 (sparse) |
| sudo usage | 0 | Every subprocess call |
| Template name accuracy | All correct | 2 wrong |
| systemctl semantics | enable/disable | start/stop/restart (wrong) |

### The Compaction Problem

Even when anti-patterns ARE embedded in the user prompt, OpenCode's
auto-compaction summarizes them away. After 2-3 compaction rounds on a
large multi-file task, the model is working from:

> "Continue building the Flask kiosk admin panel. Files written: ..."

Instead of:

> "CRITICAL: NO shell=True, ALL inputs through shlex.quote(), systemctl
> enable NOT start, template names must match EXACTLY..."

### The Fix: `-f` Attachments

OpenCode's `-f` flag attaches files as **project context** — not
conversation history. Project context survives compaction intact.
When MR-Krabs calls:

```
opencode run --model local-l0/ornith-35b -f /tmp/mrkrabs_rules.md "build..."
```

The rules file is available to the model in every turn, even after
multiple compaction rounds.

## Architecture

```
MR-Krabs orchestrator
  │
  ├── _execute_opencode_tier()
  │     │
  │     ├── _get_opencode_rules()         # loads template
  │     │     └── docs/workflow/templates/code-opencode-rules.md
  │     │
  │     ├── writes to temp file           # NamedTemporaryFile
  │     │
  │     ├── opencode run -f <temp> ...    # attaches as project context
  │     │
  │     └── cleanup: os.unlink(temp)      # removes temp file after run
  │
  └── _execute_pi_tier()
        │
        └── --append-system-prompt ...    # PI: system-level quality rules
```

### Key Design Decision: Temp File vs Persistent File

The rules file is written to a **temp file** (deleted after each run),
not a persistent location. Why:

1. **No polluting the project root.** The rules file is MR-Krabs internal
   infrastructure, not user-visible project configuration.

2. **Atomic updates.** If the rules template changes between runs,
   each invocation gets the latest version automatically — no stale
   cached files.

3. **No git pollution.** Temp files in /tmp don't appear in `git status`.

4. **No cross-task contamination.** If two MR-Krabs tasks run
   concurrently, they get independent temp files.

## Maintenance Guide (for other agents)

### When to Add a Rule

Add a rule when you observe a **recurring anti-pattern** in OpenCode's
output across multiple tasks. The threshold is:

- ✅ Same class of bug appears in 2+ independent coding tasks
- ✅ The bug is system-administration related (shell commands, configs)
- ✅ The bug would be caught by PI's "production quality" rules

Examples from the E2E testing:

| Anti-pattern | Spotted in | Rule added |
|---|---|---|
| `sudo` on every subprocess | Wired, WiFi, System Info pages | "NEVER call commands with sudo" |
| `systemctl start` instead of `enable` | Kiosk toggle, network config | "systemctl: use enable/disable" |
| Missing shlex.quote() | All subprocess calls | "ALL user inputs through shlex.quote()" |
| Wrong template names | system.html vs system_info.html | "Template filenames: use EXACTLY" |
| Missing POST routes | users, wired config endpoints | "Implement ALL routes specified" |

### When NOT to Add a Rule

- ❌ One-off bug in a specific task — fix the task spec, not the global rules
- ❌ Purely algorithmic errors — the model's code was just wrong
- ❌ Rules that contradict OpenCode's normal behavior — you'll fight the
  system prompt

### Rule Format

Each rule follows this structure:

```markdown
- **Short imperative statement**
  > One-sentence explanation of WHY.
  > Counter-example: what the model commonly does wrong.
```

Rules are organized by domain section:

| Section | Applies to |
|---|---|
| Subprocess Safety | Any code calling subprocess, os.system, shell commands |
| System Administration | systemctl, usermod, nmcli, iwconfig, network tools |
| File & Template Integrity | Flask/Django/Jinja2 templates, static assets |
| API & Route Completeness | REST endpoints, form handlers |
| Code Quality | All code (always apply) |
| HTML/JS Specific | Frontend code only |
| Python/Flask Specific | Python backend code |
| Testing | Test files |

### Rules File Location

```
docs/workflow/templates/code-opencode-rules.md
```

This path is resolved by `_get_opencode_rules()` relative to
`self.workflow_dir` (which is `{project_root}/docs/workflow`).

### Verifying Rules Are Active

Check the orchestrator logs. A successful OpenCode invocation with
rules attached prints:

```
[DIAG] l0-coder r1: opencode model=local-l0/ornith-35b, prompt=12345chars, ...
```

The rules file is silently attached — no additional log line
(by design, to keep output clean). To verify the file was written
and attached, add temporary debug logging to `_execute_opencode_tier`:

```python
print(f"  [RULES] attached: {len(rules_content)}chars → {rules_path}")
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Rules not applied (model still uses sudo) | rules template missing or empty | Check `docs/workflow/templates/code-opencode-rules.md` exists |
| OpenCode error: "file not found: /tmp/mrkrabs..." | Temp file cleaned up too early | Rules file deleted AFTER subprocess.run completes — shouldn't happen |
| Compaction still drops rules | OpenCode version changed `-f` semantics | Re-test with current OpenCode version |

## Human-Facing Explanation

When a human (user, teammate, code reviewer) asks why OpenCode output
quality varies, here's the explanation:

---

**"OpenCode and PI produce different code quality from the same model
because their system prompts have opposite philosophies."**

OpenCode's built-in prompt prioritizes speed and conciseness ("DO NOT
ADD ANY COMMENTS", "minimize output tokens"). PI's prompt prioritizes
completeness and safety ("handle edge cases", "validate inputs",
"production quality").

**"To close the gap, MR-Krabs attaches a project coding standards file
to every OpenCode run using the `-f` flag."** OpenCode treats attached
files as permanent project context — they survive the automatic
conversation summarization that would otherwise drop anti-pattern
rules by the third compaction round.

**"This is the same pattern as CLAUDE.md or .cursorrules — a file of
project-specific coding standards that the agent reads before every
task. The difference is that MR-Krabs manages it automatically rather
than requiring the user to maintain it."**

The rules file lives at `docs/workflow/templates/code-opencode-rules.md`
and covers: shell safety (shlex.quote, no shell=True, no sudo), system
administration conventions (systemctl enable/disable, usermod -aG),
template naming accuracy, API route completeness, and general code
quality standards.

---

## Related Files

| File | Purpose |
|---|---|
| `docs/workflow/templates/code-opencode-rules.md` | The rules template (source of truth) |
| `docs/workflow/templates/code-pi-system-prompt.md` | PI's system prompt (for comparison) |
| `docs/workflow/templates/code-system-prompt.md` | Generic system prompt (non-PI fallback) |
| `src/core/orchestrator.py:_get_opencode_rules()` | Loads the rules template |
| `src/core/orchestrator.py:_execute_opencode_tier()` | Writes temp file, attaches via -f |
