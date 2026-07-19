#!/usr/bin/env python3
"""C3 take 2 — use multi-pass (7 files needs splitting)."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

DIR = '/home/sblanken/workspace/mrkrabs-challenge-3-chaos-daemon'
spec = open(os.path.join(DIR, 'SPEC.md')).read()

from src.core.orchestrator import LLMOrchestrator
orch = LLMOrchestrator()
start = time.monotonic()

result = orch.execute_with_judge(
    task_id='c3-chaos-v5',
    context={
        'task_spec': spec,
        'spec': {
            'success_criteria': [
                'app.py uses get_service_address() instead of hardcoded hosts',
                'registry.py has POST /register, GET /services/<name>, GET /services',
                'sidecar.py heartbeats every 2s and deregisters on SIGTERM',
                'fallback.py provides in-memory cache when Redis is down',
                'test_registry.py passes all 7 tests',
                'Zero external Python dependencies beyond stdlib',
            ],
            'constraints': [
                'Python stdlib only — no requests, no flask',  
                'Use urllib.request for HTTP calls instead of requests library',
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
    json.dump({'challenge':'c3-v5','success':result.get('success'),
        'tier':str(result.get('tier_used','')),'retries':result.get('retries',0),
        'score':result.get('judge_score'),'elapsed_s':elapsed,
        'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)

tr = subprocess.run(['python3','-m','pytest','test_registry.py','-v','--tb=short'],
    cwd=DIR, capture_output=True, text=True, timeout=120)
print(f"\nTests: {tr.stdout.count('PASSED')} passed, {tr.stdout.count('FAILED')} failed, exit={tr.returncode}")
if tr.returncode != 0:
    print(tr.stdout[-1500:])
