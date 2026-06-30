# MR-Krabs Coding Standards — Attached to every OpenCode invocation

<!--
  MECHANISM: This file is written to a temp file and attached to every
  OpenCode call via `opencode run -f <this_file> "<prompt>"`. It persists
  through auto-compaction because OpenCode treats -f attachments as
  project context, not conversation history.

  AGENT MAINTAINERS: When you discover a recurring anti-pattern in
  OpenCode-generated code, add it here. The rule format is:
    - Short imperative (what TO do or NOT do)
    - One-line explanation of WHY
    - Counter-example of what the model commonly produces

  HUMAN EXPLANATION: "OpenCode's built-in system prompt tells the model
  to be concise and skip comments, which causes it to skip defensive
  coding patterns. This file is attached to every coding invocation so
  the model sees these rules as permanent project context that survives
  conversation compaction. It's the same idea as a CLAUDE.md or
  .cursorrules file — project-specific coding standards that the agent
  reads before every task."
-->

# Project Coding Standards

These rules are **non-negotiable project policy**, not suggestions.
They are attached to every coding task. All tools are available to you.

---

## Subprocess Safety

- **ALL user-supplied strings passed to subprocess MUST go through `shlex.quote()`**
  > Shell injection is the #1 security bug in system-administration tools.
  > Never write `subprocess.run(f"usermod {username}")`. Always quote.

- **NEVER use `shell=True` in subprocess calls**
  > Use list-form commands: `["usermod", "-aG", group, username]`

- **NEVER call commands with `sudo`**
  > This code runs under an orchestrator that handles privileges.
  > Direct sudo in generated code breaks in containerized/remote execution.

---

## System Administration

- **systemctl: use `enable`/`disable`, NOT `start`/`stop`/`restart`**
  > Configuration tools enable/disable services for persistence.
  > Runtime control (start/stop) is for the operator, not the configurator.
  > Wrong: `systemctl start kiosk.service`
  > Right: `systemctl enable kiosk.service`

- **usermod: use `-aG` (append), NOT `-G` (replace)**
  > `-G` replaces ALL supplementary groups — it will strip sudo access.
  > Always: `usermod -aG <group> <username>`

- **nmcli: connection show uses `-f GENERAL.STATE`, not `-f 'general.status'`**
  > nmcli field names are case-sensitive. Wrong case = empty output.
  > Always test nmcli field names against the actual output format.

---

## File & Template Integrity

- **Template filenames: use EXACTLY the names specified in the task**
  > `system_info.html` is not `system.html`.
  > `users_add.html` is not `add_user.html`.
  > Mismatched template names break Flask's template resolution.

- **Verify template files exist before referencing them in routes**
  > If the task says "create templates/foo.html and add route /foo",
  > write the file FIRST, then add the route in app.py.

- **CSS and JS paths: match the EXACT static/ and templates/ structure**
  > `url_for('static', filename='css/keyboard.css')` expects the file
  > at `static/css/keyboard.css`. Create matching directory structure.

---

## API & Route Completeness

- **Implement ALL routes specified in the task**
  > Missing POST routes (e.g., POST /api/users, POST /api/wired/config)
  > are the most common incompleteness bug. If the spec says a POST
  > endpoint exists, implement it even if the logic seems implied.

- **Every form action must have a matching route**
  > `<form action="/users/add" method="POST">` requires both
  > `@app.route("/users/add")` with `methods=["GET", "POST"]`.

---

## Code Quality

- **Complete implementations — NO stubs, NO `TODO`, NO `pass`**
  > Every function body must be fully implemented.
  > If you can't finish a function, write as much as you can and note
  > what remains — the orchestrator will retry the incomplete file.

- **Validate ALL user inputs before processing**
  > Check for empty strings, invalid IPs, missing fields, type errors.
  > Return clear error messages, not 500 tracebacks.

- **Handle edge cases**
  > What if the network interface doesn't exist? What if the user list
  > is empty? What if the config file is missing?
  > Every code path must return a defined result.

- **Add docstrings to public functions**
  > One-line summary of what the function does.
  > Not a novel — just enough so the next developer knows the contract.

---

## HTML/JS Specific

- **Virtual keyboards: bind to `touchstart`, not just `click`**
  > Kiosks run on touchscreens. `click` has 300ms delay on mobile.
  > Use `element.addEventListener('touchstart', handler)`.

- **Status polling: use `setInterval`, clear on page unload**
  > `setInterval(fetchStatus, 10000)` in a page that reloads every 10s
  > without clearing the interval leaks timers. Use `clearInterval` in
  > a `beforeunload` handler or `window.addEventListener('unload', ...)`.

- **CSS: design for 48px minimum touch targets**
  > Kiosk users have large fingers. Buttons, links, and interactive
  > elements must be at least 48×48px. No tiny click targets.

---

## Python/Flask Specific

- **Use `shlex.quote()` on ALL user inputs before shell commands**
  > (Repeated because it's the #1 bug.) This applies to usermod, nmcli,
  > systemctl, iwconfig, and any other subprocess call.

- **Flask routes: return proper HTTP status codes**
  > Success: 200, 201 (created). Client error: 400, 404. Server error: 500.
  > Don't return 200 for everything with an error message in JSON.

- **Import only what you use**
  > Don't `import *`. Don't import libraries the task doesn't mention.
  > If the task spec doesn't mention a library, it's not available.

---

## Testing

- **Write test files when the task specifies them**
  > If the task says "create tests/test_smoke.py", create it.
  > Tests should exercise the happy path and at least one error path.

- **Tests must be runnable**
  > If the task specifies `pytest`, use pytest fixtures and assertions.
  > If the task specifies `python -m unittest`, use TestCase classes.
  > Don't mix frameworks in a single test file.

---

## When to Ignore These Rules

These rules apply to **system-administration code** (shell commands,
systemctl, usermod, nmcli, network management). For pure-algorithm
code (regex engines, HTTP parsers, data structures), the subprocess
and system-administration rules don't apply — use your judgment. But
the code-quality rules (complete implementations, edge cases,
docstrings) ALWAYS apply.
