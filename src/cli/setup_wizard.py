#!/usr/bin/env python3
"""Setup wizard — generates ~/.mrkrabs/config.yaml interactively.

The setup wizard can be driven by a principal agent (Hermes, Claude
Code, etc.) by loading the corresponding prompt template. Each stage
returns the questions to ask; the principal agent collects answers
and feeds them back.

Usage (principal agent):
    from src.cli.setup_wizard import SetupWizard
    wizard = SetupWizard()
    question = wizard.next_question()
    ... agent asks user, collects response ...
    wizard.answer(response)
    ... repeat until done ...
    wizard.write_config()

Usage (direct CLI):
    python -m src.cli.setup_wizard
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ── Config template ────────────────────────────────────────────────────

CONFIG_TEMPLATE = """\
version: "1.0"

# ── Providers ─────────────────────────────────────────
# {providers_note}
providers:
{providers_yaml}

# ── Models ────────────────────────────────────────────
# Each model definition maps a role-tier name to a provider
# and model ID. Roles: judge, planner, orchestrator, coder, reviewer.
models:
{models_yaml}

# ── Workflows ─────────────────────────────────────────
# Escalation chains per task type. Tiers are tried in order.
workflows:
{workflows_yaml}

# ── Tier Failure Actions ───────────────────────────────
# What happens when a tier exhausts all retries.
#   log_only           → log + continue to next tier
#   notify_and_escalate → notify + continue
#   notify_and_wait    → notify + block for human
tier_failure_actions:
{failure_actions_yaml}

# ── Budget (optional) ─────────────────────────────────
budget:
  daily_limit_usd: {daily_limit}
  budget_awareness: true
  tier_thresholds:
    0.8: l2-coder
    0.5: l1-coder
    0.3: l0-coder
"""


# ── Question definitions ────────────────────────────────────────────────


@dataclass
class SetupQuestion:
    """A single question in the setup wizard."""

    id: str
    role: str  # "judge", "l0-coder", "l0-planner", etc.
    description: str
    suggested: str  # comma-separated suggestions
    required: bool = True
    default_provider: str = "openrouter"
    default_model: str = ""


# Standard role definitions
ROLE_QUESTIONS: List[SetupQuestion] = [
    SetupQuestion(
        id="judge",
        role="Judge",
        description="Quality gate — evaluates all agent outputs. Must be a reasoning-capable model with calibrated scoring.",
        suggested="DeepSeek R1 (deepseek/deepseek-r1 via OpenRouter), Claude Sonnet 4.6 (anthropic/claude-sonnet-4.6 via OpenRouter), o4-mini (openai/o4-mini via OpenRouter)",
        default_provider="openrouter",
        default_model="deepseek/deepseek-r1",
    ),
    SetupQuestion(
        id="l0-planner",
        role="L0-Planner",
        description="Task decomposition — breaks requirements into bite-sized subtasks. First planning tier, tried before escalation.",
        suggested="Gemini 2.5 Pro (google/gemini-2.5-pro via OpenRouter), Claude-Distilled 35B (local LM Studio), Qwen30-Coder (local LM Studio)",
        default_provider="openrouter",
        default_model="google/gemini-2.5-pro",
    ),
    SetupQuestion(
        id="l1-planner",
        role="L1-Planner",
        description="Fallback planner — used when L0-Planner's plans are repeatedly rejected by the Judge.",
        suggested="Gemini 2.5 Flash (google/gemini-2.5-flash via OpenRouter), Claude Haiku 4.5 (anthropic/claude-haiku-4.5 via OpenRouter)",
        required=False,
        default_provider="openrouter",
        default_model="google/gemini-2.5-flash",
    ),
    SetupQuestion(
        id="l2-planner",
        role="L2-Planner",
        description="Last-resort planner — used when both L0 and L1 planners fail. Most expensive, most capable.",
        suggested="Claude Sonnet 4.6 (anthropic/claude-sonnet-4.6 via OpenRouter), Claude Opus 4.6 (anthropic/claude-opus-4.6 via OpenRouter)",
        required=False,
        default_provider="openrouter",
        default_model="anthropic/claude-sonnet-4.6",
    ),
    SetupQuestion(
        id="orchestrator",
        role="Orchestrator",
        description="Task routing & coordination — decomposes work and routes subtasks to coders. Not a planner — orchestrator manages execution.",
        suggested="Qwen30-Coder (local LM Studio), Gemini 2.5 Flash (via OpenRouter), Claude Sonnet 4.6 (via OpenRouter)",
        default_provider="openrouter",
        default_model="google/gemini-2.5-flash",
    ),
    SetupQuestion(
        id="l0-coder",
        role="L0-Coder",
        description="Cheapest coder — tried first for all code generation tasks. Should need tools: file_read, file_write.",
        suggested="Qwen30-Coder 30B MoE (local LM Studio), Grok 4.1 Fast (x-ai/grok-4.1-fast via OpenRouter), Qwen2.5-Coder-7B (local)",
        default_provider="openrouter",
        default_model="x-ai/grok-4.1-fast",
    ),
    SetupQuestion(
        id="l1-coder",
        role="L1-Coder",
        description="Fallback coder — used when L0-Coder's output is repeatedly rejected. Moderate cost, better quality.",
        suggested="Gemini 2.5 Flash (google/gemini-2.5-flash via OpenRouter), Claude Haiku 4.5 (anthropic/claude-haiku-4.5 via OpenRouter)",
        required=False,
        default_provider="openrouter",
        default_model="google/gemini-2.5-flash",
    ),
    SetupQuestion(
        id="l2-coder",
        role="L2-Coder",
        description="Last-resort coder — used when L0 and L1 coders fail. Most expensive, most capable.",
        suggested="Claude Sonnet 4.6 (anthropic/claude-sonnet-4.6 via OpenRouter), GPT-4o (openai/gpt-4o via OpenRouter)",
        required=False,
        default_provider="openrouter",
        default_model="anthropic/claude-haiku-4.5",
    ),
]


# ── Wizard class ────────────────────────────────────────────────────────


class SetupWizard:
    """Drives the MR-Krabs setup process.

    The principal agent calls next_question() to get the current
    question, presents it to the user, then calls answer(response)
    with the user's choice. When is_complete() returns True, call
    write_config() to persist the result.
    """

    def __init__(self):
        self._questions = list(ROLE_QUESTIONS)
        self._index = 0
        self._answers: Dict[str, Dict[str, str]] = {}
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._workflows: Dict[str, List[str]] = {
            "code": [],
            "plan": [],
        }
        self._budget_daily = "10.00"

    @property
    def current_question(self) -> Optional[SetupQuestion]:
        if self._index < len(self._questions):
            return self._questions[self._index]
        return None

    def next_question(self) -> Optional[str]:
        """Return the next question to ask, or None if complete.

        The returned string is a formatted prompt the principal agent
        can present directly to the user.
        """
        q = self.current_question
        if q is None:
            return None

        required = "(REQUIRED)" if q.required else "(OPTIONAL — press Enter to skip)"
        return (
            f"**{q.role}** {required}\n"
            f"{q.description}\n\n"
            f"Suggested: {q.suggested}\n\n"
            f"Format: `provider model`\n"
            f"  e.g. `openrouter {q.default_model}`\n"
            f"  or   `litellm mrk-{q.id}` (if using a LiteLLM virtual endpoint)\n"
            f"  or   `lmstudio_21 qwen-model-name` (direct LM Studio)\n\n"
            f"Your choice:"
        )

    def answer(self, response: str) -> bool:
        """Process the user's response. Returns True if accepted.

        Response format: "provider model" (two words)
        For optional roles, empty response means skip.
        """
        q = self.current_question
        if q is None:
            return False

        response = response.strip()

        # Empty response on optional → skip
        if not response:
            if q.required:
                return False
            self._index += 1
            return True

        parts = response.split(maxsplit=1)
        if len(parts) < 2:
            return False

        provider_name, model_id = parts[0], parts[1]

        # Determine base_url from provider name conventions
        base_url = self._infer_base_url(provider_name)

        # Register provider if new
        if provider_name not in self._providers:
            is_local = "1234" in base_url or "lmstudio" in provider_name.lower()
            self._providers[provider_name] = {
                "type": "openai_compatible",
                "base_url": base_url,
                "api_key_env": self._infer_api_key_env(provider_name),
                "timeout": 1800 if is_local else 300,
            }

        # Build model config
        tools = []
        if "coder" in q.id:
            tools = ["file_write", "file_read"]
        elif "planner" in q.id:
            tools = ["file_read"]

        self._answers[q.id] = {
            "provider": provider_name,
            "model": model_id,
            "temperature": "0.0" if q.id != "judge" else "0.1",
            "max_tokens": "32768" if "planner" in q.id or "coder" in q.id else "4096",
            "roles": [q.id.split("-")[-1] if "-" in q.id else q.id],
            "tools": tools,
        }

        # Add to workflow
        if "coder" in q.id:
            self._workflows["code"].append(q.id)
        elif "planner" in q.id:
            self._workflows["plan"].append(q.id)

        self._index += 1
        return True

    def _infer_base_url(self, provider: str) -> str:
        if provider == "openrouter":
            return "https://openrouter.ai/api/v1"
        if provider.startswith("lmstudio_"):
            octet = provider.split("_", 1)[1] if "_" in provider else "21"
            return f"http://192.168.101.{octet}:1234/v1"
        if provider == "litellm":
            return "http://localhost:4000/v1"
        # Default: assume local LM Studio
        return f"http://localhost:1234/v1"

    def _infer_api_key_env(self, provider: str) -> Optional[str]:
        if provider == "openrouter":
            return "OPENROUTER_API_KEY"
        if provider == "litellm":
            return "LITELLM_MASTER_KEY"
        return None  # local providers don't need API keys

    def is_complete(self) -> bool:
        return self._index >= len(self._questions)

    def skip_remaining(self) -> None:
        """Skip all remaining questions."""
        self._index = len(self._questions)

    def write_config(self, path: Optional[str] = None) -> Path:
        """Write the config to ~/.mrkrabs/config.yaml."""
        import textwrap

        config_path = Path(path) if path else Path.home() / ".mrkrabs" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Format providers section
        providers_yaml = ""
        for name, pdata in self._providers.items():
            providers_yaml += f"  {name}:\n"
            for k, v in pdata.items():
                if v is None:
                    continue
                if isinstance(v, str):
                    providers_yaml += f"    {k}: \"{v}\"\n"
                else:
                    providers_yaml += f"    {k}: {v}\n"

        # Format models section
        models_yaml = ""
        for role_id, mdata in self._answers.items():
            models_yaml += f"  {role_id}:\n"
            for k, v in mdata.items():
                if isinstance(v, list):
                    items = ", ".join(v)
                    models_yaml += f"    {k}: [{items}]\n"
                elif isinstance(v, str) and v.isdigit():
                    models_yaml += f"    {k}: {v}\n"
                else:
                    models_yaml += f"    {k}: \"{v}\"\n"

        # Format workflows section
        workflows_yaml = ""
        for wf_name, tiers in self._workflows.items():
            if not tiers:
                continue
            tiers.append("principal")
            workflows_yaml += f"  {wf_name}:\n"
            workflows_yaml += f"    tiers: {tiers}\n"
            workflows_yaml += f"    max_retries_per_tier: 3\n"
            workflows_yaml += f"    judge_model: judge\n"

        # Format failure actions
        failure_yaml = ""
        for role_id in self._answers:
            if role_id.startswith("l0-"):
                failure_yaml += f"  {role_id}: log_only\n"
            elif role_id.startswith("l1-"):
                failure_yaml += f"  {role_id}: notify_and_escalate\n"
            elif role_id.startswith("l2-"):
                failure_yaml += f"  {role_id}: notify_and_wait\n"

        content = CONFIG_TEMPLATE.format(
            providers_note="Declare each API endpoint once, reference by name in models.",
            providers_yaml=providers_yaml or "  # (none defined)",
            models_yaml=models_yaml or "  # (none defined)",
            workflows_yaml=workflows_yaml or "  # (none defined)",
            failure_actions_yaml=failure_yaml or "  # (none defined)",
            daily_limit=self._budget_daily,
        )

        config_path.write_text(content)
        return config_path


# ── CLI entry point ─────────────────────────────────────────────────────


def _cli():
    """Direct CLI setup wizard (not agent-driven)."""
    wizard = SetupWizard()

    print("MR-Krabs Setup Wizard")
    print("=" * 60)
    print("I'll help you define models for each pipeline role.\n")

    while not wizard.is_complete():
        prompt = wizard.next_question()
        if prompt is None:
            break

        print(prompt)
        response = input("> ").strip()

        if response.lower() in ("skip", "s"):
            wizard.answer("")
            print("  → Skipped.\n")
        elif wizard.answer(response):
            q = wizard.current_question
            if q is None:
                break
            prev = wizard._questions[wizard._index - 1]
            print(f"  ✓ {prev.role} configured.\n")
        else:
            print("  ✗ Invalid format. Use: provider model\n")

    print("=" * 60)
    path = wizard.write_config()
    print(f"\n✓ Config written to {path}")
    print("Run 'mrkrabs doctor' to validate connectivity.")


if __name__ == "__main__":
    _cli()
