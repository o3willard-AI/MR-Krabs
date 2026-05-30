#!/usr/bin/env python3
"""
Model Profiles — structured capability profiles consumed by Planner and Judge.

Each profile describes a model's known strengths, weaknesses, failure
signatures, and countermeasures so the system can:

1. The **Planner** reads profiles to decompose tasks appropriately and
   inject model-specific prepend prompts (e.g., "use nmcli -t flag").
2. The **Judge** reads profiles to give surgical feedback on known failure
   patterns on the first review instead of discovering them iteratively.

Profiles are loaded lazily and keyed by model name or alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Data structures ───────────────────────────────────────────────────


@dataclass
class KnownFailure:
    """A failure pattern the judge can detect and correct on first sight."""

    trigger: str  # Regex or substring to match in model output
    feedback: str  # Surgical correction to include in judge reply
    severity: str = "warning"  # "error" | "warning" | "info"

    def trigger_pattern(self) -> str:
        """Human-readable description of the trigger pattern."""
        if not self.trigger or self.trigger == r"":
            return "Always flag — model output is unreliable"
        return self.trigger.replace(r"\s", " ").replace(r"\b", "").strip("\\")


@dataclass
class ModelProfile:
    """Capability profile for a coding model."""

    name: str  # Model name / alias (matches MODELS key or model string)
    display_name: str  # Human-readable name
    size: str  # e.g. "9B", "20B", "30B"
    vram: str  # e.g. "~6 GB", "~12 GB"
    provider: str  # "lmstudio", "openrouter", "anthropic", etc.

    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    # Task capacity
    max_files: int = 1  # Max files model can produce in one call
    max_context_k: int = 32  # Effective context window in K tokens

    # Prompt enrichment
    prompt_prepend: str = ""  # Injected before every coding task
    system_prompt_override: str = ""  # Full override if needed

    # Judge integration
    known_failures: List[KnownFailure] = field(default_factory=list)

    # Role routing
    recommended_roles: List[str] = field(default_factory=list)
    blacklisted_roles: List[str] = field(default_factory=list)

    # Metrics (from evaluation)
    eval_ratio: str = ""  # Reasoning ratio (e.g. "0:1", "1:1")
    eval_tok_s: str = ""  # Tokens/sec
    eval_build_score: str = ""  # Files and bug count (e.g. "18/18, 0 bugs")
    eval_plan_score: str = ""  # Planning quality
    eval_judge_score: str = ""  # Judging quality

    @property
    def is_blacklisted_for(self, role: str) -> bool:
        return role in self.blacklisted_roles

    @property
    def is_recommended_for(self, role: str) -> bool:
        return role in self.recommended_roles


# ── Profile registry ──────────────────────────────────────────────────

# All profiles keyed by short alias (used in MODELS dict profile field)
PROFILES: Dict[str, ModelProfile] = {}


def register(profile: ModelProfile) -> ModelProfile:
    """Register a profile and return it for inline use."""
    PROFILES[profile.name] = profile
    return profile


def get_profile(key: str) -> Optional[ModelProfile]:
    """Look up a profile by name or alias. Returns None if not found."""
    return PROFILES.get(key)


def get_prepend(model_key: str) -> str:
    """Get the prepend prompt for a model, or empty string."""
    profile = PROFILES.get(model_key)
    return profile.prompt_prepend if profile else ""


def get_known_failures(model_key: str) -> List[KnownFailure]:
    """Get known failure patterns for the judge to check."""
    profile = PROFILES.get(model_key)
    return profile.known_failures if profile else []


def models_for_role(role: str) -> List[str]:
    """List model keys recommended for a given role."""
    return [k for k, p in PROFILES.items() if role in p.recommended_roles]


# ── Profile definitions ───────────────────────────────────────────────
# Each profile is built from evaluation data (see SKILL: multi-model-comparison)


# ═══════════════════════════════════════════════════════════════════════
# LOCAL LM STUDIO MODELS
# ═══════════════════════════════════════════════════════════════════════


SUSHI_9B = register(ModelProfile(
    name="sushi-9b",
    display_name="Qwen 3.5 Sushi Coder RL 9B",
    size="9B",
    vram="~6 GB",
    provider="lmstudio",

    strengths=[
        "single-file Flask routes",
        "error handling with try/except",
        "proper HTTP status codes",
        "shlex.quote on user inputs",
        "clean Python structure",
    ],
    weaknesses=[
        "multi-file projects (fails beyond 3 files)",
        "nmcli parsing (uses human-readable output, not -t flag)",
        "shell=True usage (should use list form)",
        "systemd/nmcli API knowledge gaps",
        "omits host/port on app.run()",
    ],

    max_files=3,
    max_context_k=32,

    prompt_prepend=(
        "CRITICAL RULES FOR THIS TASK:\n"
        "1. Use `nmcli -t` (terse mode) for colon-delimited parseable output. "
        "Split on ':', not spaces.\n"
        "2. NEVER use `shell=True` in subprocess calls — always use list form.\n"
        "3. For WiFi connect: `nmcli device wifi connect SSID password PASSWORD` "
        "(separate arguments, not password=VALUE).\n"
        "4. app.run() MUST include `host='0.0.0.0', port=5000`.\n"
    ),

    known_failures=[
        KnownFailure(
            trigger=r"shell\s*=\s*True",
            feedback=(
                "Replace `shell=True` with list-form subprocess call. "
                "Example: `subprocess.run(['nmcli', '-t', 'device', 'status'], "
                "capture_output=True, text=True)`"
            ),
            severity="error",
        ),
        KnownFailure(
            trigger=r"\.split\s*\(\s*\)",
            feedback=(
                "Don't split nmcli output on spaces — use `nmcli -t` flag for "
                "colon-delimited output and split on ':'. Example: "
                "`nmcli -t -f DEVICE,TYPE,STATE device status`"
            ),
            severity="error",
        ),
        KnownFailure(
            trigger=r"app\.run\s*\(\s*debug\s*=\s*True\s*\)",
            feedback=(
                "Add `host='0.0.0.0'` and `port=5000` to app.run(): "
                "`app.run(host='0.0.0.0', port=5000, debug=True)`"
            ),
            severity="warning",
        ),
    ],

    recommended_roles=["l0-coder"],
    blacklisted_roles=["planner", "judge"],

    eval_ratio="0:1",
    eval_tok_s="~30 tok/s",
    eval_build_score="1 file, correct structure",
    eval_plan_score="N/A (too small)",
    eval_judge_score="N/A (too small)",
))


QWEN_12B_HERETIC = register(ModelProfile(
    name="qwen-12b-heretic",
    display_name="Qwen 3.6 12B Heretic Thinking",
    size="12B",
    vram="~8 GB",
    provider="lmstudio",

    strengths=[
        "reasoning structure (systematic thinking)",
        "low VRAM footprint",
    ],
    weaknesses=[
        "hallucinates concepts and API details",
        "confidently produces wrong output",
        "judging: invents non-existent bugs",
        "planning: wrong dependency chains, incorrect API names",
        "code generation: produces function stubs, fills rest with reasoning",
    ],

    max_files=0,
    max_context_k=32,

    known_failures=[
        KnownFailure(
            trigger=r"",  # Always flag — this model is unreliable
            feedback=(
                "OUTPUT REJECTED: Model is known to hallucinate. "
                "Escalate to next tier or request human review. "
                "Do not accept any code, plan, or judgment from this model."
            ),
            severity="error",
        ),
    ],

    recommended_roles=[],
    blacklisted_roles=["coder", "planner", "judge", "reviewer", "orchestrator"],

    eval_ratio="26:1 at 200 tok, ~1:1 at 4K tok",
    eval_tok_s="~3 tok/s effective",
    eval_build_score="N/A (incapable)",
    eval_plan_score="2/10 (hallucinates)",
    eval_judge_score="2/10 (hallucinates)",
))


GPTOSS_20B = register(ModelProfile(
    name="gpt-oss-20b",
    display_name="GPT-OSS 20B Claude Opus Distill",
    size="20B",
    vram="~12 GB",
    provider="lmstudio",

    strengths=[
        "multi-file project structure (18/18 files)",
        "clean anti-pattern avoidance (no render_template_string, single Flask)",
        "shlex.quote on all user inputs",
        "password confirmation checks",
        "planning and orchestration quality",
        "good task decomposition with dependency analysis",
    ],
    weaknesses=[
        "Flask API details: Response.json doesn't exist, needs .get_json()",
        "pwd.getgrouplist signature: takes gid, not 0",
        "systemctl toggle doesn't exist — use enable/disable",
        "usermod -G replaces groups — needs -aG to append",
        "skips nmcli con down/up cycle for config changes",
        "takes prefix directly instead of netmask→CIDR conversion",
        "judging: hallucinates line-level issues, misses real bugs",
    ],

    max_files=18,
    max_context_k=32,

    prompt_prepend=(
        "CRITICAL PYTHON/FLASK RULES:\n"
        "1. Flask Response objects use `.get_json()` not `.json`.\n"
        "2. `pwd.getgrouplist(name, gid)` — second arg is gid (e.g., user's pw_gid), not 0.\n"
        "3. systemctl uses `enable`/`disable`, NOT `toggle`.\n"
        "4. `usermod -aG` to append groups; `-G` alone replaces all groups.\n"
        "5. After nmcli connection modifications, cycle: `nmcli con down NAME` then `nmcli con up NAME`.\n"
        "6. Convert netmask to CIDR: `ipaddress.ip_network(f'0.0.0.0/{netmask}').prefixlen`.\n"
    ),

    known_failures=[
        KnownFailure(
            trigger=r"\.json\b(?!ify\b)",
            feedback=(
                "Flask Response objects don't have `.json` attribute. "
                "Use `.get_json()` to parse JSON response body, or call the "
                "underlying function directly rather than through the route."
            ),
            severity="error",
        ),
        KnownFailure(
            trigger=r"getgrouplist\([^,]+,\s*0\s*\)",
            feedback=(
                "`pwd.getgrouplist(name, 0)` — second arg should be the user's "
                "gid, not 0. Use `pwd.getgrouplist(u.pw_name, u.pw_gid)`."
            ),
            severity="error",
        ),
        KnownFailure(
            trigger=r"systemctl\s+toggle",
            feedback=(
                "`systemctl toggle` doesn't exist. Use `systemctl enable SERVICE` "
                "or `systemctl disable SERVICE`. To toggle: check current state "
                "with `is-enabled`, then enable or disable accordingly."
            ),
            severity="error",
        ),
        KnownFailure(
            trigger=r"usermod\s+-G\s",
            feedback=(
                "`usermod -G` replaces ALL supplementary groups. Use `usermod -aG` "
                "to append the user to a new group without removing existing memberships."
            ),
            severity="error",
        ),
    ],

    recommended_roles=["planner", "orchestrator"],
    blacklisted_roles=["judge"],

    eval_ratio="0:1",
    eval_tok_s="~56 tok/s",
    eval_build_score="18/18 files, 6 runtime bugs",
    eval_plan_score="8/10",
    eval_judge_score="3/10 (hallucinates)",
))


# ═══════════════════════════════════════════════════════════════════════
# VAST.AI / HIGH-END LOCAL MODELS (baselines for comparison)
# ═══════════════════════════════════════════════════════════════════════


CODER_30B = register(ModelProfile(
    name="coder-30b",
    display_name="Qwen3-Coder-30B-A3B (MoE)",
    size="30B",
    vram="~19 GB",
    provider="lmstudio",

    strengths=[
        "complete multi-file builds (18/18 files)",
        "zero anti-patterns",
        "correct nmcli usage",
        "correct netmask→CIDR conversion",
    ],
    weaknesses=[
        "one shlex.quote in JavaScript (minor)",
        "needs 19 GB VRAM (above 12-16 GB target)",
    ],

    max_files=18,
    max_context_k=32,

    known_failures=[],

    recommended_roles=["l0-coder", "l1-coder"],
    blacklisted_roles=[],

    eval_ratio="0:1",
    eval_tok_s="48 tok/s",
    eval_build_score="18/18 files, 0 bugs",
    eval_plan_score="N/A (not tested)",
    eval_judge_score="N/A (not tested)",
))


CLAUDE_OPUS_35B = register(ModelProfile(
    name="claude-opus-35b",
    display_name="Qwen3.6-35B-A3B Claude-Distilled (MoE)",
    size="35B",
    vram="~21 GB",
    provider="lmstudio",

    strengths=[
        "best hybrid model: coding + judging",
        "18/18 build with 0 anti-patterns",
        "54-issue code review in 13s",
        "196 tok/s (fastest tested)",
        "planning and orchestration quality",
    ],
    weaknesses=[
        "needs 21 GB VRAM (above 12-16 GB target)",
    ],

    max_files=18,
    max_context_k=32,

    known_failures=[],

    recommended_roles=["l0-coder", "l1-coder", "planner", "judge"],
    blacklisted_roles=[],

    eval_ratio="1.6:1",
    eval_tok_s="196 tok/s",
    eval_build_score="18/18 files, 0 bugs",
    eval_plan_score="9/10",
    eval_judge_score="8/10",
))


# ═══════════════════════════════════════════════════════════════════════
# CLOUD MODELS (OpenRouter)
# ═══════════════════════════════════════════════════════════════════════


GEMINI_25_PRO = register(ModelProfile(
    name="gemini-2.5-pro",
    display_name="Gemini 2.5 Pro",
    size="—",
    vram="—",
    provider="openrouter",

    strengths=[
        "planning and task decomposition",
        "large context window (1M tokens)",
        "structured output adherence",
    ],
    weaknesses=[
        "not a coder — use for planning only",
    ],

    max_files=0,
    max_context_k=1000,

    known_failures=[],

    recommended_roles=["planner", "orchestrator"],
    blacklisted_roles=["coder"],

    eval_ratio="—",
    eval_tok_s="—",
    eval_build_score="N/A (planner)",
    eval_plan_score="Proven in MR-Krabs pipeline",
    eval_judge_score="N/A (not used as judge)",
))


DEEPSEEK_R1 = register(ModelProfile(
    name="deepseek-r1",
    display_name="DeepSeek R1",
    size="—",
    vram="—",
    provider="openrouter",

    strengths=[
        "calibrated judging scores",
        "actionable structured critiques",
        "reasoning depth",
    ],
    weaknesses=[
        "slow compared to non-reasoning judges",
        "higher cost per critique",
    ],

    max_files=0,
    max_context_k=128,

    known_failures=[],

    recommended_roles=["judge"],
    blacklisted_roles=["coder"],

    eval_ratio="—",
    eval_tok_s="—",
    eval_build_score="N/A (judge)",
    eval_plan_score="N/A (judge)",
    eval_judge_score="Production MR-Krabs judge",
))
