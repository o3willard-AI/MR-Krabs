"""Fail-now and fail-up signals for preemptive tier escalation.

FailNow: nuclear option — skip ALL tiers, jump to specified tier, one shot, no judge.
FailUp:   unstick me — abort current tier, advance ONE level, resume normal escalation.
"""

import os
from pathlib import Path
import json

# ── FailNow state ────────────────────────────────────────────────

_fail_now_tier: str | None = None

def set_fail_now(tier: str) -> None:
    """Activate fail-now for the next ask() call. Clears after use."""
    global _fail_now_tier
    _fail_now_tier = tier

def clear_fail_now() -> None:
    """Manually clear the fail-now signal."""
    global _fail_now_tier
    _fail_now_tier = None

def get_fail_now() -> str | None:
    """Check fail-now: env var overrides function call."""
    env_tier = os.environ.get("MRKRABS_FAIL_NOW")
    if env_tier:
        return env_tier
    return _fail_now_tier

def is_fail_now_active() -> bool:
    """Check if fail-now is currently active."""
    return get_fail_now() is not None

# ── FailUp state ─────────────────────────────────────────────────

_fail_up_active: bool = False

def set_fail_up() -> None:
    """Activate fail-up: abort current tier, advance one level."""
    global _fail_up_active
    _fail_up_active = True

def clear_fail_up() -> None:
    """Clear the fail-up signal (auto-cleared after each tier bump)."""
    global _fail_up_active
    _fail_up_active = False

def is_fail_up_active() -> bool:
    """Check if fail-up is currently active (env var or function)."""
    if os.environ.get("MRKRABS_FAIL_UP"):
        return True
    return _fail_up_active

# ── Mesh signal check ────────────────────────────────────────────

def check_mesh_fail_now() -> str | None:
    """Check for fail-now signal from agent mesh.

    Convention: agents post to mrkrabs://fail-now topic with JSON {"tier": "L3-Coder"}.
    This function checks a well-known file ~/.mrkrabs/fail_now_signal.json.
    """
    signal_file = Path(os.path.expanduser("~/.mrkrabs/fail_now_signal.json"))
    if signal_file.exists():
        try:
            data = json.loads(signal_file.read_text())
            tier = data.get("tier")
            signal_file.unlink()  # consume the signal
            if tier:
                set_fail_now(tier)
                return tier
        except Exception:
            pass
    return None

def check_mesh_fail_up() -> bool:
    """Check for fail-up signal from agent mesh.

    Convention: agents post to mrkrabs://fail-up topic.
    Checks ~/.mrkrabs/fail_up_signal.json — any valid JSON activates fail-up.
    """
    signal_file = Path(os.path.expanduser("~/.mrkrabs/fail_up_signal.json"))
    if signal_file.exists():
        try:
            signal_file.unlink()  # consume the signal
            set_fail_up()
            return True
        except Exception:
            pass
    return False