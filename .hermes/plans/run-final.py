#!/usr/bin/env python3
"""Final unified challenge run — L0 + L1/L2 tiers with all fixes active."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

from src.core.orchestrator import LLMOrchestrator

CHALLENGES = [
    {
        'id': 'c1', 'name': 'Reconciliation Engine',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-1-state-engine',
        'test': ['python3', '-m', 'pytest', 'test_reconcile.py', '-v', '--tb=short'],
        'success': ['All tests pass', 'Zero deps', 'Idempotent', 'Dry-run safe', 'Rollback works'],
        'timeout': 2400,
    },
    {
        'id': 'c2', 'name': 'LLM Gateway',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-2-llm-gateway',
        'test': ['python3', '-m', 'pytest', 'test_gateway.py', '-v', '--tb=short'],
        'success': ['All tests pass', 'Stdlib only', 'SSE streaming', 'Failover works', 'Telemetry complete'],
        'timeout': 2400,
    },
    {
        'id': 'c3', 'name': 'Chaos Daemon',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-3-chaos-daemon',
        'test': ['python3', '-m', 'pytest', 'test_registry.py', '-v', '--tb=short'],
        'success': ['All tests pass', 'app uses get_service_address()', 'Registry works', 'Stdlib only', 'Thread-safe'],
        'timeout': 3600,
    },
]

results = {}

for ch in CHALLENGES:
    print(f"\n{'='*60}")
    print(f"  {ch['name']} — L0→L1→L2 escalation, all fixes active")
    print(f"{'='*60}")

    spec = open(os.path.join(ch['dir'], 'SPEC.md')).read()
    orch = LLMOrchestrator()
    start = time.monotonic()

    result = orch.execute_with_judge(
        task_id=f"{ch['id']}-final",
        context={
            'task_spec': spec,
            'spec': {
                'success_criteria': ch['success'],
                'constraints': ['Python stdlib only', 'No external packages'],
            },
        },
        tiers=['l0-coder', 'l1-coder', 'l2-coder', 'principal'],
        max_retries_per_tier=3,
        judge_model='judge',
        project_root=ch['dir'],
        timeout_seconds=ch['timeout'],
    )

    elapsed = time.monotonic() - start
    success = result.get('success')

    print(f"  Result: success={success}, tier={result.get('tier_used')}, "
          f"retries={result.get('retries',0)}, score={result.get('judge_score')}, "
          f"duration={elapsed:.0f}s")

    files = result.get('files', {})
    for p in sorted(files.keys())[:10]:
        print(f"    {p} ({len(files[p])} bytes)")

    with open(os.path.join(ch['dir'], 'mrkrabs_result.json'), 'w') as f:
        json.dump({'challenge':ch['id'], 'success':success,
            'tier':str(result.get('tier_used','')), 'retries':result.get('retries',0),
            'score':result.get('judge_score'), 'elapsed_s':elapsed,
            'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)

    # Run tests
    test_file = ch['test'][-1]
    if os.path.exists(os.path.join(ch['dir'], test_file)):
        tr = subprocess.run(ch['test'], cwd=ch['dir'], capture_output=True, text=True, timeout=120)
        p = tr.stdout.count('PASSED')
        f_count = tr.stdout.count('FAILED')
        print(f"  Tests: {p} passed, {f_count} failed, exit={tr.returncode}")
        if tr.returncode != 0:
            print(tr.stdout[-800:])

    results[ch['id']] = {'name': ch['name'], 'success': success, 'elapsed_s': elapsed}

# Summary
print(f"\n{'='*60}")
print("  FINAL RESULTS")
print(f"{'='*60}")
for cid, r in results.items():
    status = 'PASS' if r['success'] else 'FAIL'
    print(f"  [{status}] {r['name']}: {r['elapsed_s']:.0f}s")
