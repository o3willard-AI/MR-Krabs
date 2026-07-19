#!/usr/bin/env python3
"""Run all challenges L0-only — OpenRouter tiers are non-functional via OpenCode."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

from src.core.orchestrator import LLMOrchestrator

CHALLENGES = [
    {
        'id': 'c1', 'name': 'Reconciliation Engine',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-1-state-engine',
        'files': ['reconcile.py', 'test_reconcile.py'],
        'test': ['python3', '-m', 'pytest', 'test_reconcile.py', '-v', '--tb=short'],
        'success': ['All pytest tests pass', 'Zero deps (stdlib)', 'Idempotent', 'Dry-run safe', 'Rollback works'],
        'timeout': 2400,
    },
    {
        'id': 'c2', 'name': 'LLM Gateway',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-2-llm-gateway',
        'files': ['gateway.py', 'test_gateway.py'],
        'test': ['python3', '-m', 'pytest', 'test_gateway.py', '-v', '--tb=short'],
        'success': ['All tests pass', 'Stdlib only', 'SSE streaming', 'Failover works', 'Telemetry complete'],
        'timeout': 2400,
    },
    {
        'id': 'c3', 'name': 'Chaos Daemon',
        'dir': '/home/sblanken/workspace/mrkrabs-challenge-3-chaos-daemon',
        'files': ['registry.py', 'sidecar.py', 'fallback.py', 'chaos_test.py', 'test_registry.py', 'app.py', 'docker-compose.yml'],
        'test': ['python3', '-m', 'pytest', 'test_registry.py', '-v', '--tb=short'],
        'success': ['All tests pass', 'app uses get_service_address()', 'Registry works', 'Stdlib only', 'Thread-safe'],
        'timeout': 3600,
    },
]

results = {}

for ch in CHALLENGES:
    print(f"\n{'='*60}")
    print(f"  {ch['name']} — L0-only, PI on .23")
    print(f"{'='*60}")
    
    spec = open(os.path.join(ch['dir'], 'SPEC.md')).read()
    orch = LLMOrchestrator()
    start = time.monotonic()
    
    result = orch.execute_with_judge(
        task_id=f"{ch['id']}-l0only",
        context={
            'task_spec': spec,
            'spec': {
                'success_criteria': ch['success'],
                'constraints': ['Python stdlib only', 'No external packages'],
            },
        },
        tiers=['l0-coder'],        # L0 only — L1/L2 OpenRouter broken via OpenCode
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
    
    # Save result
    with open(os.path.join(ch['dir'], 'mrkrabs_result.json'), 'w') as f:
        json.dump({'challenge':ch['id'], 'success':success,
            'tier':str(result.get('tier_used','')), 'retries':result.get('retries',0),
            'score':result.get('judge_score'), 'elapsed_s':elapsed,
            'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)
    
    # Run tests
    if os.path.exists(os.path.join(ch['dir'], ch['test'][-1])):
        tr = subprocess.run(ch['test'], cwd=ch['dir'], capture_output=True, text=True, timeout=120)
        p = tr.stdout.count('PASSED') if 'PASSED' in tr.stdout else tr.stdout.count('passed')
        f_count = tr.stdout.count('FAILED') if 'FAILED' in tr.stdout else tr.stdout.count('failed')
        print(f"  Tests: {p} passed, {f_count} failed, exit={tr.returncode}")
        if tr.returncode != 0:
            print(tr.stdout[-1000:])
    
    results[ch['id']] = {
        'name': ch['name'], 'success': success,
        'elapsed_s': elapsed, 'tests': f'{p} pass, {f_count} fail' if 'p' in dir() else 'N/A',
    }

# Summary
print(f"\n{'='*60}")
print("  SUMMARY")
print(f"{'='*60}")
for cid, r in results.items():
    status = '✅' if r['success'] else '❌'
    print(f"  {status} {r['name']}: {r['tests']} in {r['elapsed_s']:.0f}s")
