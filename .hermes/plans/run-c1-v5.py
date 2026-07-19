#!/usr/bin/env python3
"""C1 take 2 — use multi-pass (file extraction filter is fixed now)."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

DIR = '/home/sblanken/workspace/mrkrabs-challenge-1-state-engine'
spec = open(os.path.join(DIR, 'SPEC.md')).read()

from src.core.orchestrator import LLMOrchestrator
orch = LLMOrchestrator()
start = time.monotonic()

result = orch.execute_with_judge(
    task_id='c1-reconcile-v5',
    context={
        'task_spec': spec,
        'spec': {
            'success_criteria': [
                'All pytest tests pass', 'Zero dependencies (stdlib only)',
                'Idempotent execution', 'Dry-run creates no files',
                'Rollback on failure leaves FS untouched',
            ],
        },
    },
    tiers=['l0-coder', 'l1-coder', 'l2-coder', 'principal'],
    max_retries_per_tier=3, judge_model='judge',
    project_root=DIR, timeout_seconds=2400,
)

elapsed = time.monotonic() - start
print(f"\n=== C1 RESULT: success={result.get('success')}, tier={result.get('tier_used')}, "
      f"retries={result.get('retries',0)}, score={result.get('judge_score')}, "
      f"duration={elapsed:.0f}s")

files = result.get('files', {})
for p in sorted(files.keys()):
    print(f"  {p} ({len(files[p])} bytes)")

with open(os.path.join(DIR, 'mrkrabs_result.json'), 'w') as f:
    json.dump({'challenge':'c1-v5','success':result.get('success'),
        'tier':str(result.get('tier_used','')),'retries':result.get('retries',0),
        'score':result.get('judge_score'),'elapsed_s':elapsed,
        'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)

tr = subprocess.run(['python3','-m','pytest','test_reconcile.py','-v','--tb=short'],
    cwd=DIR, capture_output=True, text=True, timeout=120)
print(f"\nTests: {tr.stdout.count('PASSED')} passed, {tr.stdout.count('FAILED')} failed, exit={tr.returncode}")
if tr.returncode != 0:
    print(tr.stdout[-1500:])
