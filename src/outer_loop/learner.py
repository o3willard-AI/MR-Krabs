#!/usr/bin/env python3
"""Learner — failure analysis → rule generation for the outer loop.

Every verifier rejection feeds the learner. It analyzes:
- What failed (the symptom)
- Why (wrong chunk boundary, missed dependency, etc.)
- What rule would have prevented it

Over 6–12 projects, the rule library converges. The decomposer consults it
before making chunking decisions.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from src.outer_loop.pattern_library import (
    DecompositionRule,
    FailureRecord,
    PatternLibrary,
    log_failure,
    read_failure_log,
)
from src.outer_loop.models import get_outer_loop_models


# ── OpenAI-compatible LLM call ──────────────────────────────────────────────


def _call_llm(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Call an OpenAI-compatible LLM for learner analysis.

    Uses the provider config from ~/.mrkrabs/config.yaml or defaults.
    """
    try:
        from src.core.config_loader import get_config
        config = get_config()
        provider_cfg = config.providers.get(provider)
        if provider_cfg:
            base_url = provider_cfg.base_url
            api_key = provider_cfg.api_key or os.environ.get(
                provider_cfg.api_key_env or "", "dummy"
            )
        else:
            # Default to known local endpoints
            base_url = f"http://192.168.101.{provider.split('-')[-1]}:1234/v1"
            api_key = "dummy"
    except Exception:
        base_url = f"http://192.168.101.{provider.split('-')[-1]}:1234/v1"
        api_key = "dummy"

    import urllib.request

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()

    url = f"{base_url.rstrip('/')}/chat/completions"
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"LLM call failed ({provider}/{model}): {e}")


# ── Learner ─────────────────────────────────────────────────────────────────


FAILURE_TYPES = {
    "seam_mismatch": (
        "Two chunks were supposed to connect but their interfaces didn't match. "
        "Chunk A exported one thing; chunk B expected something else."
    ),
    "missing_dep": (
        "A chunk needed a file/function from another chunk that wasn't "
        "assigned to the same chunk or a declared dependency."
    ),
    "over_chunk": (
        "A chunk was too large — the coder couldn't handle all files "
        "in one pass and either missed some or produced low quality output."
    ),
    "under_chunk": (
        "A chunk was too small — splitting related files across chunks "
        "created unnecessary complexity and integration friction."
    ),
}


def analyze_failure(
    failure: FailureRecord,
    library: PatternLibrary,
) -> Optional[DecompositionRule]:
    """Analyze a verifier rejection and generate a decomposition rule.

    Uses the learner LLM to understand why the decomposition failed,
    then synthesizes a structured rule that would prevent similar failures.

    Args:
        failure: The failure record from the verifier
        library: Current pattern library for context

    Returns:
        A new or updated DecompositionRule, or None if no rule could be generated
    """
    models = get_outer_loop_models()
    learner_model = models.get("learner")
    if not learner_model:
        return None

    # Build context about existing rules
    existing_rules_context = ""
    if library.rule_count() > 0:
        existing_rules_context = "Existing rules:\n"
        for rule in library.rules.values():
            existing_rules_context += (
                f"  - [{rule.id}] WHEN {rule.condition} THEN {rule.action}"
                f"  (confidence: {rule.confidence:.0%})\n"
            )

    failure_type_desc = FAILURE_TYPES.get(
        failure.failure_type, "Unknown failure type"
    )

    system_prompt = """You are a decomposition rule synthesizer for MR-Krabs, 
an AI-powered coding pipeline. Your job is to analyze WHY a task decomposition 
failed and generate a structured rule that would prevent similar failures.

Output a JSON object with these fields:
- "root_cause": why the decomposition failed (1-2 sentences)
- "condition": a rule condition like "file_count > 20" or "has_shared_imports == true"
- "action": a rule action like "group by directory, max 15 files per chunk"
- "rule_id": a short kebab-case identifier for this rule

Rules must be simple and mechanical — the decomposer applies them deterministically.
Focus on file count thresholds, directory groupings, dependency clustering, and
cross-cutting concern detection.

Only output valid JSON, no other text."""

    user_prompt = f"""Failure to analyze:

Type: {failure.failure_type}
Description: {failure_type_desc}
Detail: {failure.detail}
Affected files: {', '.join(failure.affected_files) if failure.affected_files else 'none'}
Chunks used: {', '.join(failure.chunks)}

{existing_rules_context}

Analyze this failure and generate a rule that would prevent it. Output JSON only."""

    try:
        response = _call_llm(
            provider=learner_model.provider,
            model=learner_model.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=learner_model.temperature,
            max_tokens=learner_model.max_tokens,
        )

        # Extract JSON from response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            return None

        data = json.loads(response[json_start:json_end])

        rule = DecompositionRule(
            id=data.get("rule_id", f"rule-{failure.project_id}"),
            condition=data.get("condition", ""),
            action=data.get("action", ""),
            examples=[failure.project_id],
            success_count=0,
            failure_count=1,
        )

        # Check if this duplicates or extends an existing rule
        for existing_id, existing_rule in library.rules.items():
            if existing_rule.condition == rule.condition:
                # Extend existing rule
                existing_rule.failure_count += 1
                if failure.project_id not in existing_rule.examples:
                    existing_rule.examples.append(failure.project_id)
                library.save()
                return existing_rule

        # New rule
        library.add_rule(rule)
        return rule

    except Exception as e:
        print(f"[LEARNER] Failed to analyze failure: {e}")
        return None


def process_new_failures(library: PatternLibrary) -> int:
    """Process any unprocessed failures in the failure log.

    Reads the failure log, finds entries that haven't been analyzed yet,
    and runs the learner on each one. Returns the number of rules generated.

    Args:
        library: The pattern library to update

    Returns:
        Number of new rules generated
    """
    from src.outer_loop.pattern_library import read_failure_log

    failures = read_failure_log(limit=20)
    processed_ids = {r for rule in library.rules.values() for r in rule.examples}
    new_rules = 0

    for record in failures:
        pid = record.get("project_id", "")
        if pid in processed_ids:
            continue

        failure = FailureRecord(
            project_id=pid,
            spec_hash=record.get("spec_hash", ""),
            chunks=record.get("chunks", []),
            failure_type=record.get("failure_type", ""),
            detail=record.get("detail", ""),
            affected_files=record.get("affected_files", []),
            resolution=record.get("resolution", ""),
            generated_rule=record.get("generated_rule", ""),
            timestamp=record.get("timestamp", ""),
        )

        rule = analyze_failure(failure, library)
        if rule:
            new_rules += 1
            print(f"[LEARNER] Generated rule: {rule.id} ({rule.condition} → {rule.action})")

    return new_rules


def generate_learning_summary(library: PatternLibrary) -> str:
    """Generate a human-readable summary of the learning state.

    Returns:
        Markdown summary of rules, their confidence, and convergence state
    """
    if library.rule_count() == 0:
        return "No decomposition rules learned yet. The outer loop is operating in baseline mode."

    lines = [
        f"## Outer Loop Learning State",
        f"",
        f"**{library.rule_count()} rules** learned from "
        f"**{library.decomposition_count()} decompositions**.",
        f"",
        f"| Rule | Condition | Action | Confidence | Examples |",
        f"|------|-----------|--------|------------|----------|",
    ]

    for rule in sorted(library.rules.values(), key=lambda r: r.confidence, reverse=True):
        confidence_pct = f"{rule.confidence:.0%}"
        examples_str = ", ".join(rule.examples[:3])
        if len(rule.examples) > 3:
            examples_str += f", +{len(rule.examples) - 3} more"
        lines.append(
            f"| {rule.id} | {rule.condition} | {rule.action} "
            f"| {confidence_pct} | {examples_str} |"
        )

    lines.extend([
        "",
        f"**Convergence**: {'Reached' if library.rule_count() >= 6 else 'In progress'} "
        f"({library.rule_count()}/6 rules target for first-pass accuracy)",
    ])

    return "\n".join(lines)
