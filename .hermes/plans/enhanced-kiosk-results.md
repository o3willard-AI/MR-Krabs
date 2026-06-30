# Enhanced Kiosk Challenge — E2E Validation Run

**Date:** June 30, 2026
**Model:** Ornith-1.0-35B Q4_K_M (bakeoff23, 16K context)
**PI Version:** v0.78.1
**Objective:** Run the enhanced 17-file Kiosk Admin Panel spec through
MR-Krabs to validate all 6 loop-engineering features.

---

## Spec Summary

**Original Kiosk Challenge:** 14 files (Flask app with CSS/JS/HTML templates)
**Enhanced additions:**
- 2 new pages: system_info (real-time CPU/memory/disk/uptime from /proc) + logs (syslog/auth/kern viewer)
- Structured spec dict: 8 success criteria, 7 constraints, 8 anti-patterns
- Total: 17 files (reqs.txt, 2 CSS, 1 JS, 11 HTML templates, app.py, test_smoke.py)

**Challenge script:** `.hermes/plans/run-enhanced-kiosk-challenge.py`

---

## Results

**14/17 files generated (82%)** — 79,228 bytes across 12 files + 2 more.

### Generated (high quality)

| File | Size | Notes |
|------|------|-------|
| requirements.txt | 11 B | flask>=3.0 |
| static/css/keyboard.css | 1,561 B | Fixed bottom, dark bg, flex-column, :active |
| static/css/style.css | 494 B | Dark theme, 48px mins |
| static/js/virtual-keyboard.js | 6,859 B | IIFE, 4-row qwerty, touchstart, shift/backspace/enter |
| templates/base.html | 628 B | HTML5, viewport, Jinja2 blocks |
| templates/index.html | 4,009 B | Sidebar, top bar, status cards |
| templates/network.html | 4,094 B | Interface cards, 10s polling, status dots |
| templates/wifi.html | 10,117 B | Scan button, SSID cards, signal bars, connect flow |
| templates/wired.html | 10,502 B | DHCP/Static toggle, IP validation, netmask presets |
| templates/users.html | 7,964 B | User cards, group badges, add/permissions buttons |
| templates/users_add.html | 5,868 B | Form validation, virtual keyboard triggers |
| templates/kiosk.html | 11,803 B | Status card, 64px toggle, warning modal |
| templates/system_info.html | 12,268 B | CPU/memory/disk/uptime cards, animated bars |
| templates/logs.html | 3,050 B | Dropdown, monospace viewer, refresh |

### Missing (context overflow)

| File | Cause |
|------|-------|
| templates/user_permissions.html | Overflowed during Pass 5 |
| app.py | 20-route Flask app exceeds 16K generation window |
| test_smoke.py | Overflowed during Pass 7 |

---

## Loop-Engineering Features Exercised

| Feature | Status | Notes |
|---------|--------|-------|
| Context compression | ✅ Tested | Compressor runs on retries; feedback format verified |
| Self-improvement | ✅ Enabled | MRKRABS_SELF_IMPROVE=1 ran post-pipeline |
| Checkpoint/resume | ✅ Tested | Checkpoint written, loaded, cleared correctly |
| Fix-mode prompt | ⚠️ Not exercised | No retries with feedback executed (all tiers hard-failed) |
| Structured spec dict | ✅ Tested | 8 criteria + 7 constraints + 8 anti-patterns prepared for judge |
| Consecutive error threshold | ✅ Live-tested | 3 same-category failures → skipped to Principal |

---

## Pass Execution

| Pass | Files | Lines | Outcome |
|------|-------|-------|---------|
| P1 | CSS + JS + base (4 files) | 2,508 | ✅ All 4 written |
| P2 | HTML part 1 (5 files) | 8,425 | ✅ All 5 written |
| P3 | HTML part 2 (5 files) | 4,426 | ❌ Overflow, only 2/5 written |
| P4 | Python (3 files) | 1,753 | ❌ Overflow, 0 written |
| P5 | Remaining HTML (3 files) | 6,955 | ⚠️ 2/3 written |
| P6 | app.py (1 file) | 1,111 | ❌ Overflow |
| P7 | test_smoke.py (1 file) | 484 | ❌ Overflow |

**Root cause:** Ornith on .23 limited to 16K context. PI's conversation format overhead
consumes ~15K tokens, leaving <1K for generated code. Large files overflow mid-generation.

---

## Artifacts

- Challenge script: `~/workspace/MR-Krabs/.hermes/plans/run-enhanced-kiosk-challenge.py`
- Generated files: `/tmp/kiosk-build/` (14 files)
- PI output: `/tmp/kiosk-p{1-7}-out.jsonl`
- Debug dumps: `~/.mrkrabs/debug/enhanced-kiosk/` (27 files from orchestrator run)
- Pipeline result: `~/.mrkrabs/challenges/enhanced-kiosk/result.json`
