#!/usr/bin/env python3
"""Run ThrottleProxy coding tasks through MR-Krabs tier escalation."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["OPENROUTER_API_KEY"] = open(os.path.expanduser("~/.openrouter-key")).read().strip()

from src import ask

TASKS = [
    {
        "name": "day1_rate_limiter",
        "prompt": """Write a Python module `limiter.py` for a multi-tenant API rate-limiting gateway.

Requirements:
1. Sliding window rate limiter class with per-tenant counters
2. Configurable: requests/minute, tokens/minute, concurrent requests
3. Tenant identified by API key (string)
4. Thread-safe counter implementation using threading.Lock
5. Clean API: check_rate_limit(tenant_id: str) -> RateLimitResult
6. RateLimitResult should be a dataclass with: allowed (bool), remaining (int), reset_at (float), retry_after (float)
7. Include type hints throughout

Write ONLY the complete `limiter.py` file, no explanation. Include all imports."""
    },
    {
        "name": "day3_tenant_store",
        "prompt": """Write a Python module `tenant_store.py` for a multi-tenant API gateway.

Requirements:
1. SQLite-backed tenant storage using sqlite3
2. Tenant dataclass with: id, name, api_key, tier (gold/silver/bronze), created_at, active
3. CRUD operations: create_tenant, get_tenant, list_tenants, update_tenant, delete_tenant
4. API key generation using secrets module (32-char hex)
5. Tier-based rate limit lookup: gold=1000/min, silver=100/min, bronze=10/min
6. Context manager for database connections
7. Type hints throughout

Write ONLY the complete `tenant_store.py` file, no explanation. Include all imports."""
    },
]

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "throttle_proxy_output")
os.makedirs(OUT_DIR, exist_ok=True)

results = []

for task in TASKS:
    print(f"\n{'='*60}")
    print(f"Task: {task['name']}")
    print(f"{'='*60}")

    start = time.time()
    result = ask(task["prompt"], auto_escalate=True)
    elapsed = time.time() - start

    # Save output to file
    out_path = os.path.join(OUT_DIR, f"{task['name']}.py")
    with open(out_path, "w") as f:
        f.write(result.output)

    entry = {
        "task": task["name"],
        "tier": result.tier,
        "model": result.model,
        "cost": result.cost,
        "success": result.success,
        "attempts": result.attempts,
        "duration_seconds": result.duration_seconds,
        "output_chars": len(result.output),
        "output_file": out_path,
    }
    results.append(entry)

    print(f"  Tier:     {result.tier}")
    print(f"  Model:    {result.model}")
    print(f"  Cost:     ${result.cost:.6f}")
    print(f"  Attempts: {result.attempts}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Output:   {len(result.output)} chars → {out_path}")
    print(f"  Success:  {result.success}")

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
total_cost = sum(r["cost"] for r in results)
tiers_used = set(r["tier"] for r in results)
print(f"Tasks:     {len(results)}")
print(f"Passed:    {sum(1 for r in results if r['success'])}")
print(f"Total cost: ${total_cost:.6f}")
print(f"Tiers used: {sorted(tiers_used)}")
for r in results:
    print(f"  {r['task']:20s} → {r['tier']:10s} {r['model']:30s} ${r['cost']:.6f}")
