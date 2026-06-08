#!/usr/bin/env python3
"""MR-Krabs Challenge Gauntlet — 4 challenges exercising the PI coder pipeline.

Runs each challenge through L0 (free local) first, escalates to L1/L2 on failure.
Outputs a results table.

Usage:
    cd ~/workspace/MR-Krabs
    export LITELLM_MASTER_KEY="mox-agent-clubhouse-master-key-2026"
    export OPENROUTER_API_KEY="$(cat ~/.hermes/secrets/openrouter-api-key)"
    PYTHONPATH=src:$PYTHONPATH python scripts/gauntlet.py
"""
import json
import os
import sys
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Environment
os.environ.setdefault("LITELLM_MASTER_KEY", "mox-agent-clubhouse-master-key-2026")
_or_key = os.path.expanduser("~/.hermes/secrets/openrouter-api-key")
if os.path.exists(_or_key) and "OPENROUTER_API_KEY" not in os.environ:
    os.environ["OPENROUTER_API_KEY"] = open(_or_key).read().strip()

from src.core.orchestrator import LLMOrchestrator


CHALLENGES = [
    {
        "id": "file-stats",
        "name": "CLI File Stats Tool",
        "spec": """Write a Python CLI tool called file_stats.py that accepts file paths and glob patterns as arguments,
counts lines, words, characters, and bytes for each file, and outputs the results as JSON.

Requirements:
- Accept file paths and/or glob patterns on the command line (sys.argv)
- For each file: count lines, words, characters, bytes
- Output a JSON object like: {"files": [{"path": "...", "lines": N, "words": N, "chars": N, "bytes": N}]}
- Handle FileNotFoundError gracefully — skip missing files with an error entry
- Stdlib only (glob, json, pathlib, sys, os)

Also create test_file_stats.py with pytest tests covering:
- Temp file with known content (verify counts)
- FileNotFoundError handling
- Glob pattern expansion
- Empty file handling""",
    },
    {
        "id": "config-validator",
        "name": "Config File Validator",
        "spec": """Write a Python module called config_validator.py that validates a TOML config file against a schema dict.

Requirements:
- Function validate_config(filepath: str, schema: dict) -> list[dict]
- Returns a list of error dicts: [{"key": "section.key", "error": "message"}], empty list if valid
- Schema format: {"section": {"key": type}} where type is str, int, float, bool, list, or dict
- Handle missing file (return one error entry)
- Handle malformed TOML (return one error entry)
- Check for missing required keys and type mismatches
- Stdlib only (tomllib, pathlib)

Also create test_config_validator.py with pytest tests covering:
- Valid config file (no errors)
- Missing required key
- Wrong type
- Non-existent file
- Malformed TOML""",
    },
    {
        "id": "kv-store",
        "name": "HTTP Key-Value Store",
        "spec": """Write a Flask-based HTTP key-value store called kv_store.py.

Requirements:
- Flask app factory: create_app()
- GET /api/key/<key> — return JSON {"key": key, "value": value} or 404 {"error": "not found"}
- POST /api/key/<key> with JSON body {"value": "..."} — create/update key
- DELETE /api/key/<key> — delete key, return 204
- GET /api/keys — list all keys
- In-memory store (dict), no persistence needed
- Proper Content-Type: application/json headers
- Input validation: reject non-JSON POST bodies
- Deps: Flask>=3.1 (add to a requirements.txt)

Also create test_kv_store.py with pytest tests using the Flask test client:
- Create a key via POST
- Read it back via GET
- Update it via POST
- Delete it via DELETE (verify 204)
- Read deleted key (verify 404)
- List all keys
- POST with non-JSON body (verify 400)
- POST with missing "value" field (verify 400)""",
    },
    {
        "id": "password-checker",
        "name": "Password Strength Checker",
        "spec": """Write a password strength checker called password_checker.py.

Requirements:
- Function check_strength(password: str) -> dict with:
  - "entropy_bits": float — Shannon entropy of the password
  - "crack_time_seconds": float — estimated time to crack at 1e9 guesses/sec
  - "classes": list[str] — character classes used (lowercase, uppercase, digit, special)
  - "length": int — password length
  - "score": str — one of "very weak", "weak", "fair", "strong", "very strong"
- Function generate_password(length=16, classes=None) -> str — generate random password
  - classes: list of character class names to include (default all)
  - Uses secrets module, not random
- Score thresholds: <28 bits = very weak, <36 = weak, <60 = fair, <80 = strong, >=80 = very strong
- Stdlib only (math, secrets, string)

Also create test_password_checker.py with at least 25 pytest tests covering:
- Entropy calculation for known strings
- All 5 score levels
- Crack time calculation
- Character class detection (all 4 classes)
- Password generation default length
- Password generation with specific classes only
- Empty password handling
- Edge cases: all same char, very long passwords, special chars""",
    },
]


def run_challenge(orch, challenge, tiers=None, max_retries=2):
    """Run a single challenge through the pipeline."""
    if tiers is None:
        tiers = ["l0-coder", "l1-coder", "l2-coder", "principal"]

    start = time.time()
    try:
        result = orch.execute_with_judge(
            task_id=challenge["id"],
            context={"task_spec": challenge["spec"]},
            task_type="code",
            tiers=tiers,
            max_retries_per_tier=max_retries,
            judge_model="judge",
        )
    except Exception as e:
        result = {"success": False, "error": str(e), "tier_used": None}

    elapsed = time.time() - start
    result["elapsed"] = elapsed
    result["challenge"] = challenge["name"]
    return result


def format_result(r):
    """Format a single result line."""
    success = r.get("success", False)
    tier = r.get("tier_used") or "FAIL"
    attempts = r.get("attempts_total", 0)
    elapsed = r.get("elapsed", 0)
    name = r.get("challenge", "?")

    status = "✓" if success else "✗"
    tier_short = tier.replace("-Coder", "").replace("-coder", "") if tier else "N/A"

    # Get output summary
    output = r.get("output", "") or ""
    summary = ""
    if output:
        # Extract first meaningful line
        lines = [l for l in output.split("\n") if l.strip() and not l.startswith("#")]
        summary = lines[0][:60] if lines else ""

    return f"{status} {name:30s} {tier_short:5s}  {attempts:2d} att  {elapsed:5.0f}s  {summary}"


def main():
    print("=" * 80)
    print(f"MR-Krabs Challenge Gauntlet — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Tiers: L0 (free local qwen3-coder-30b) → L1 (deepseek-v4-flash) → L2 (mimo-v2.5)")
    print("=" * 80)
    print()

    orch = LLMOrchestrator()
    print(f"PI models: {json.dumps(orch.pi_models, indent=2)}")
    print(f"PI timeouts: {json.dumps(orch.pi_timeouts, indent=2)}")
    print()

    results = []
    total_start = time.time()

    for i, challenge in enumerate(CHALLENGES, 1):
        print(f"[{i}/{len(CHALLENGES)}] {challenge['name']}...", flush=True)
        result = run_challenge(orch, challenge)
        results.append(result)
        print(f"  {format_result(result)}")
        print()

    total_time = time.time() - total_start

    # Summary table
    print("=" * 80)
    print("GAUNTLET RESULTS")
    print("=" * 80)
    passed = sum(1 for r in results if r.get("success"))
    l0_count = sum(1 for r in results if r.get("tier_used", "").lower() in ("l0-coder",))
    l1_count = sum(1 for r in results if r.get("tier_used", "").lower() in ("l1-coder",))
    l2_count = sum(1 for r in results if r.get("tier_used", "").lower() in ("l2-coder",))

    for r in results:
        print(f"  {format_result(r)}")

    print()
    print(f"Passed: {passed}/{len(CHALLENGES)}")
    print(f"L0 handled: {l0_count}/{len(CHALLENGES)}")
    print(f"L1 handled: {l1_count}/{len(CHALLENGES)}")
    print(f"L2 handled: {l2_count}/{len(CHALLENGES)}")
    print(f"Total time: {total_time:.0f}s")
    print()

    # Save detailed results
    out_path = os.path.expanduser("~/.mrkrabs/gauntlet-results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "total_time": total_time,
                "passed": passed,
                "total": len(CHALLENGES),
                "challenges": [
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "success": r.get("success"),
                        "tier": r.get("tier_used"),
                        "attempts": r.get("attempts_total"),
                        "elapsed": r.get("elapsed"),
                        "verdict_score": r.get("verdict", {}).get("score") if r.get("verdict") else None,
                    }
                    for c, r in zip(CHALLENGES, results)
                ],
            },
            f,
            indent=2,
            default=str,
        )
    print(f"Detailed results saved to {out_path}")

    return 0 if passed == len(CHALLENGES) else 1


if __name__ == "__main__":
    sys.exit(main())
