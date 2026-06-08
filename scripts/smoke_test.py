#!/usr/bin/env python3
"""Single-challenge smoke test — Config File Validator through L0."""
import os, sys, json, time

os.environ["LITELLM_MASTER_KEY"] = "mox-agent-clubhouse-master-key-2026"
_or_key = os.path.expanduser("~/.hermes/secrets/openrouter-api-key")
if os.path.exists(_or_key):
    os.environ["OPENROUTER_API_KEY"] = open(_or_key).read().strip()

sys.path.insert(0, "/home/sblanken/workspace/MR-Krabs/src")
from src.core.orchestrator import LLMOrchestrator

orch = LLMOrchestrator()
print(json.dumps({"pi_models": orch.pi_models, "pi_timeouts": orch.pi_timeouts}), flush=True)

spec = (
    "Write a Python module called config_validator.py that validates a TOML config file against a schema dict.\n\n"
    "Requirements:\n"
    "- Function validate_config(filepath: str, schema: dict) -> list[dict]\n"
    "- Returns a list of error dicts: [{'key': 'section.key', 'error': 'message'}], empty list if valid\n"
    "- Schema format: {'section': {'key': type}} where type is str, int, float, bool, list, or dict\n"
    "- Handle missing file (return one error entry)\n"
    "- Handle malformed TOML (return one error entry)\n"
    "- Check for missing required keys and type mismatches\n"
    "- Stdlib only (tomllib, pathlib)\n\n"
    "Also create test_config_validator.py with pytest tests:\n"
    "- Valid config file (no errors)\n"
    "- Missing required key\n"
    "- Wrong type\n"
    "- Non-existent file\n"
    "- Malformed TOML"
)

print(f"Running: Config File Validator (L0, 1 retry)...", flush=True)
start = time.time()

result = orch.execute_with_judge(
    task_id="config-validator-smoke",
    context={"task_spec": spec},
    task_type="code",
    tiers=["l0-coder"],
    max_retries_per_tier=1,
    judge_model="judge",
)

elapsed = time.time() - start
print(f"ELAPSED: {elapsed:.0f}s", flush=True)
print(f"SUCCESS: {result.get('success')}", flush=True)
print(f"TIER: {result.get('tier_used')}", flush=True)
print(f"ATTEMPTS: {result.get('attempts_total')}", flush=True)

verdict = result.get('verdict', {})
if isinstance(verdict, dict):
    print(f"SCORE: {verdict.get('score')}", flush=True)
    critique = str(verdict.get('critique', ''))
    if critique:
        print(f"CRITIQUE: {critique[:500]}", flush=True)

output = result.get('output', '') or ''
print(f"OUTPUT: {output[:800]}", flush=True)

esc = result.get('escalation_path', [])
print(f"ESCALATION: {esc}", flush=True)

escalated = result.get('escalated_to_principal')
print(f"ESCALATED_TO_PRINCIPAL: {escalated}", flush=True)
