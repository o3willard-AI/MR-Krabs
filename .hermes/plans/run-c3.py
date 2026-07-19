#!/usr/bin/env python3
"""Run Challenge 3 through MR-Krabs with audit + verify + retry enabled."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

DIR = '/home/sblanken/workspace/mrkrabs-challenge-3-chaos-daemon'
spec = open(os.path.join(DIR, 'SPEC.md')).read()

from src.core.orchestrator import LLMOrchestrator
orch = LLMOrchestrator()
start = time.monotonic()

result = orch.execute_with_judge(
    task_id='c3-chaos-v4',
    context={
        'task_spec': spec,
        '_multi_pass_child': True,
        'files': [
            'registry.py', 'sidecar.py', 'fallback.py',
            'chaos_test.py', 'test_registry.py',
            'app.py', 'docker-compose.yml'
        ],
        'spec': {
            'success_criteria': [
                'app.py uses get_service_address() instead of hardcoded hosts',
                'registry.py has POST /register, GET /services/<name>, GET /services',
                'sidecar.py heartbeats every 2s and deregisters on SIGTERM',
                'fallback.py provides in-memory cache when Redis is down',
                'chaos_test.py runs concurrent requests with docker stop mid-stream',
                'test_registry.py passes all 7 tests',
                'Zero external Python dependencies beyond stdlib',
            ],
            'constraints': [
                'Python stdlib only — no external packages (no requests, no flask)',
                'All service communication via HTTP',
                'Registry must be thread-safe',
            ],
        },
    },
    tiers=['l0-coder', 'l1-coder', 'l2-coder', 'principal'],
    max_retries_per_tier=3, judge_model='judge',
    project_root=DIR, timeout_seconds=3600,
)

elapsed = time.monotonic() - start
print(f"\n=== C3 RESULT: success={result.get('success')}, tier={result.get('tier_used')}, "
      f"retries={result.get('retries',0)}, score={result.get('judge_score')}, "
      f"duration={elapsed:.0f}s")

files = result.get('files', {})
for p in sorted(files.keys()):
    print(f"  {p} ({len(files[p])} bytes)")

with open(os.path.join(DIR, 'mrkrabs_result.json'), 'w') as f:
    json.dump({'challenge':'c3','success':result.get('success'),
        'tier':str(result.get('tier_used','')),'retries':result.get('retries',0),
        'score':result.get('judge_score'),'elapsed_s':elapsed,
        'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)

tr = subprocess.run(['python3','-m','pytest','test_registry.py','-v','--tb=short'],
    cwd=DIR, capture_output=True, text=True, timeout=120)
print(f"\nTests: {tr.stdout.count('PASSED')} passed, {tr.stdout.count('FAILED')} failed, exit={tr.returncode}")
if tr.returncode != 0:
    print(tr.stdout[-1500:])
