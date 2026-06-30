#!/usr/bin/env python3
"""Enhanced Kiosk Challenge — MR-Krabs E2E Validation Test.

Runs the standard 14-file Kiosk Admin Panel spec PLUS 2 new stories
(system info dashboard + log viewer). Exercises all 6 loop-engineering
features: context compression, self-improvement, checkpoint/resume,
fix-mode prompt, structured task contracts, consecutive error threshold.

Usage:
    # Set up env
    export LITELLM_MASTER_KEY="mox-agent-clubhouse-master-key-2026"

    # Run
    cd ~/workspace/MR-Krabs
    python3 .hermes/plans/run-enhanced-kiosk-challenge.py
"""

import os
import sys
import time
import json
import shutil
import tempfile
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────
# Ensure we can import from the MR-Krabs repo
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
os.chdir(str(_REPO_ROOT))

from src.core.orchestrator import LLMOrchestrator

# Output dir
OUTDIR = Path.home() / ".mrkrabs" / "challenges" / "enhanced-kiosk"
OUTDIR.mkdir(parents=True, exist_ok=True)

# ── Enhanced Task Spec ──────────────────────────────────────────────

KIOSK_SPEC = r"""# Kiosk Admin Panel — Build Specification
## Target: Python Flask web app for Ubuntu touchscreen system administration

---
CONSTRAINTS (read first):
- ONE file = one file. NO redefining `app = Flask(__name__)` multiple times in app.py.
- ALL imports at top of file. ALL routes on ONE Flask app instance.
- Server-only logic stays server-side. NO `shlex.quote()` in JavaScript.
- NO `render_template_string()` — use `render_template('file.html')` with actual template files.
- Python stdlib only: flask, subprocess, shlex, ipaddress, pwd, re, json, os, time, pathlib.
- `app.run(host='0.0.0.0', port=5000, debug=True)` at bottom of app.py, guarded by `if __name__ == '__main__':`.
- ALL files MUST be complete. NO placeholders, NO "# implement later", NO "// TODO".
- Output format: ```language:relative/path\n...complete code...\n``` fences. NO commentary text.
- Include kiosk-admin.service systemd unit file inline in app.py comments.
---
FILES TO CREATE (in dependency order):

## 1. requirements.txt
```
flask>=3.0
```

## 2. static/css/keyboard.css
- Fixed bottom bar: `position:fixed; bottom:0; width:100%; z-index:9999`
- Dark bg: #16213e. Key size: min 48x48px. Rounded corners. 4px gap.
- Touch feedback: key press briefly lightens background (`:active` pseudo-class).
- Slide-up transition when shown. Hidden by default (`display:none`).
- Keyboard uses `display:flex; flex-direction:column`.

## 3. static/css/style.css
- Dark theme: body bg #1a1a2e, text #e0e0e0, accent #0f3460
- font-family: sans-serif. margin: 0. min-height: 100vh.
- ALL interactive elements: min-height 48px, min-width 48px.
- ZERO hover styles (touchscreen). Use :active only.

## 4. static/js/virtual-keyboard.js
- Vanilla JS, zero deps. Self-initializes on DOMContentLoaded.
- Keyboard DIV appended to document.body.
- 4 rows of keys: row1=qwertyuiop, row2=asdfghjkl, row3=shift + zxcvbnm,. + backspace, row4=1234567890 + enter + [space].
- Events: `touchstart` (NOT click) on each key.
- Shift toggles uppercase for next keypress only. Backspace removes last char. Enter triggers form submit.
- Show keyboard on input focus (document.activeElement). Hide on tap outside any input/textarea.
- Keyboard hidden by default (display:none).

## 5. templates/base.html
- Standard HTML5 boilerplate with meta viewport, title block, content block.
- Links to both CSS files in head. Script tag for JS at body end.

## 6. templates/index.html
- Extends the base layout. Dashboard: top bar (48px) with hamburger + title + status dot.
- Sliding sidebar with nav items for all pages.
- Overlay closes sidebar on tap.
- Main: "System Dashboard" heading + quick-status cards for Network, WiFi, Users, Kiosk.
- Fetches dashboard API endpoint for live data.

## 7. app.py — THE ONLY Python file
Single Flask app with ALL routes. Structure:
- Imports at top: flask, subprocess, shlex, ipaddress, pwd, re, os, json, time, pathlib
- Routes: index(/), network_page(/network), network_status(/api/network/status),
  wifi_page(/wifi), wifi_scan(/api/wifi/scan), wifi_connect(POST /api/wifi/connect),
  wired_page(/wired), wired_config(POST /api/network/wired),
  users_page(/users), list_users(/api/users), create_user(POST /api/users),
  users_add_page(/users/add), permissions_page(/users/<username>/permissions),
  get_permissions(/api/users/<username>/permissions), set_permissions(POST /api/users/<username>/permissions),
  kiosk_page(/kiosk), kiosk_status(/api/kiosk/status), kiosk_toggle(POST /api/kiosk/toggle),
  dashboard_api(/api/dashboard),
  system_info_page(/system), system_info_api(/api/system/info),
  logs_page(/logs), logs_api(/api/logs)
- All subprocess calls use shlex.quote() on user inputs
- All nmcli calls use -t flag for parseable output
- Password handling: confirm_password must match. chpasswd via stdin, not cmdline.
- Usermod uses -aG (append), NOT -G (replace)
- systemctl uses enable/disable, not toggle
- nmcli con modifications: cycle down then up

## 8. templates/network.html
- Extends base.html. "Network Status" heading.
- Fetches /api/network/status on load + every 10s.
- Each interface: card with name(bold), type badge, status dot, IP, MAC.
- Summary: default gateway, DNS.
- Empty state if array empty.

## 9. templates/wifi.html
- "WiFi Configuration" heading. "Scan for Networks" button (≥48px).
- Results: scrollable cards with SSID, signal bars, lock icon.
- Tap to expand with password input + "Connect" button.
- All input fields trigger virtual keyboard.

## 10. templates/wired.html
- "Wired Network Configuration" heading.
- Interface dropdown (from /api/network/status, filtered ethernet).
- Mode toggle: DHCP / Static IP.
- Static fields: IP, Netmask (preset buttons /24 /16 /8), Gateway, DNS.
- Client-side IP format validation. All fields trigger virtual keyboard.

## 11. templates/users.html
- "User Management" heading. "Add User" button.
- User cards: username, home path, groups as badges.
- "Edit Permissions" button on each card.

## 12. templates/users_add.html
- "Create New User" heading.
- Fields: Username, Full Name, Password, Confirm Password. All trigger virtual keyboard.
- Client-side validation: username regex, passwords match.
- Cancel link → /users.

## 13. templates/user_permissions.html
- "Permissions for {{username}}" heading. Back link.
- Checkbox list of groups ≥48px touch targets.
- "Save Permissions" button.

## 14. templates/kiosk.html
- "Kiosk Mode" heading.
- Large status card with toggle switch ≥64px.
- WARNING modal before toggling.

## 15. templates/system_info.html
- "System Information" heading.
- Fetches /api/system/info on load + every 5s.
- Cards: CPU usage (percentage bar + model name), Memory (used/total bar), Disk (used/total per mount), Uptime (days/hours/minutes), Load average.
- Percentage bars: green <50%, yellow 50-80%, red >80%. Animated width transition.
- Uses text from /proc/cpuinfo, /proc/meminfo, /proc/loadavg, /proc/uptime for data.

## 16. templates/logs.html
- "System Logs" heading.
- Dropdown: syslog, auth.log, kern.log.
- Fetches /api/logs?file=<name>&lines=<n>.
- Scrollable log viewer: monospace, dark bg, color-coded severity (ERROR=red, WARN=yellow, INFO=green).
- "Refresh" button. Lines count selector (50/100/200).
- All touch targets ≥48px.

## 17. test_smoke.py
- Standalone test script. Starts app.py as subprocess. Polls :5000 until ready (max 10s).
- Tests: all 9 pages return 200. All 8 API endpoints return 200/valid JSON.
- Content checks: "Kiosk Admin Panel" on /, "Network Status" on /network,
  "virtual-keyboard.js" and "keyboard.css" in / source.
- API structure: /api/network/status has "interfaces", /api/users returns JSON array,
  /api/system/info has "cpu", "memory", "uptime".
- Print "X passed, Y failed". Exit 0 if all pass.

---
ANTI-PATTERNS (DO NOT DO):
1. NEVER define Flask app more than once — single instance only.
2. NEVER put server code (subprocess, pwd, shlex) in JS or templates.
3. NEVER use render_template_string — always reference actual template files.
4. NEVER use shlex.quote in browser JavaScript — Python module only.
5. NEVER skip template files — create the HTML file for every route.
6. NEVER leave placeholder or TODO comments.
7. NEVER double-define the same route.
8. NEVER use shell=True in subprocess calls.
9. NEVER use usermod -G (always -aG to append groups).
10. NEVER use systemctl toggle (use enable or disable).

OUTPUT FORMAT:
For each file, output exactly:
```language:relative/path
complete file contents
```
NO explanatory text between files. ALL code, no prose.
"""

# ── Structured Task Contract ────────────────────────────────────────

KIOSK_SPEC_DICT = {
    "success_criteria": [
        "All 17 files are complete with zero placeholders or TODO markers",
        "app.py has exactly ONE `app = Flask(__name__)` instance with all routes",
        "Every route has a corresponding template file (no render_template_string)",
        "All subprocess calls use shlex.quote() on user inputs",
        "All nmcli commands use -t flag for parseable colon-delimited output",
        "system_info page reads from /proc filesystem (not psutil)",
        "logs page supports syslog, auth.log, and kern.log with line count selector",
        "test_smoke.py verifies all 9 pages return 200 and all 8 API endpoints return valid JSON",
    ],
    "constraints": [
        "Python stdlib only — flask, subprocess, shlex, ipaddress, pwd, re, json, os, time, pathlib",
        "No shell=True in any subprocess call",
        "No render_template_string() anywhere",
        "usermod uses -aG not -G",
        "systemctl uses enable/disable not toggle",
        "All interactive elements have min-height/min-width 48px",
        "ZERO hover styles — use :active only",
    ],
    "anti_patterns": [
        "app = Flask(__name__) defined more than once",
        "render_template_string() used instead of render_template()",
        "shell=True in subprocess",
        "shlex.quote() in JavaScript",
        "usermod -G (missing -a flag)",
        "systemctl toggle",
        "TODO or placeholder comments",
        "CSS hover pseudo-classes",
    ],
}


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Enhanced Kiosk Challenge — MR-Krabs E2E Validation")
    print("=" * 60)
    print(f"Output dir: {OUTDIR}")
    print(f"Spec size:  {len(KIOSK_SPEC)} chars")
    print(f"Files:      17 (14 original + 2 system_info/logs + test_smoke)")
    print(f"Spec dict:  {len(KIOSK_SPEC_DICT['success_criteria'])} criteria, "
          f"{len(KIOSK_SPEC_DICT['constraints'])} constraints, "
          f"{len(KIOSK_SPEC_DICT['anti_patterns'])} anti-patterns")
    print()

    # Enable self-improvement
    os.environ["MRKRABS_SELF_IMPROVE"] = "1"

    # Enable prompt flow debug
    os.environ["MRKRABS_PROMPT_FLOW_DEBUG"] = "1"

    # Ensure LiteLLM key is available
    if "LITELLM_MASTER_KEY" not in os.environ:
        os.environ["LITELLM_MASTER_KEY"] = "mox-agent-clubhouse-master-key-2026"

    orch = LLMOrchestrator()

    # Create a clean temp directory for the build — prevents OpenCode
    # from analyzing existing files instead of writing new ones.
    build_dir = Path(tempfile.mkdtemp(prefix="kiosk-challenge-"))
    print(f"  Build dir:  {build_dir}")
    print()

    # Clean any stale checkpoints
    orch._clear_checkpoint("enhanced-kiosk")

    print("Starting pipeline...")
    print(f"  Tiers:     L0-Coder → Principal")
    print(f"  Retries:   3 per tier")
    print(f"  Plan:      auto (deterministic splitter for >20 files)")
    print(f"  Self-improve: MRKRABS_SELF_IMPROVE=1")
    print(f"  Debug:     MRKRABS_PROMPT_FLOW_DEBUG=1")
    print()

    start = time.monotonic()

    result = orch.execute_with_judge(
        task_id="enhanced-kiosk",
        context={
            "task_spec": KIOSK_SPEC,
            "spec": KIOSK_SPEC_DICT,
        },
        task_type="code",
        tiers=["l0-coder", "principal"],
        max_retries_per_tier=3,
        judge_model="judge",
        timeout_seconds=600,
        plan_first=False,
        project_root=str(build_dir),
    )

    elapsed = time.monotonic() - start

    # ── Save results ────────────────────────────────────────────────
    result_path = OUTDIR / "result.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    # ── Print summary ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success:      {result['success']}")
    print(f"Tier used:    {result.get('tier_used', 'none')}")
    print(f"Attempts:     {result.get('attempts_total', 0)}")
    print(f"Duration:     {elapsed:.1f}s")
    print(f"Score:        {result.get('score', 'N/A')}")
    print(f"Escalation:   {result.get('escalation_path', [])}")
    print(f"To Principal: {result.get('escalated_to_principal')}")

    files = result.get("files", {})
    if files:
        print(f"\nFiles written: {len(files)}")
        for path in sorted(files.keys()):
            size = len(files[path])
            print(f"  {path} ({size} bytes)")

    cost = result.get("cost_summary", {})
    if cost:
        print(f"\nEstimated cost: ${cost.get('daily_total', 'N/A')}")

    # ── Emit verdict path ───────────────────────────────────────────
    if result.get("escalation_path"):
        print(f"\nPipeline path: {' → '.join(result['escalation_path'])}")

    # ── Checkpoint status ────────────────────────────────────────────
    ck = orch._load_checkpoint("enhanced-kiosk")
    if ck:
        print(f"\nCheckpoint: {ck.get('elapsed_seconds', 0):.0f}s elapsed, "
              f"{len(ck.get('accumulated_files', {}))} files accumulated")
    else:
        print("\nCheckpoint: cleared (successful completion)")

    print(f"\nFull result: {result_path}")
    print(f"Debug dumps: ~/.mrkrabs/debug/enhanced-kiosk/")

    return result


if __name__ == "__main__":
    main()
