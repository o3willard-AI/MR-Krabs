#!/usr/bin/env python3
"""Run Challenge 2 through MR-Krabs with audit + verify + retry enabled."""
import os, sys, json, time, subprocess

os.environ['LITELLM_MASTER_KEY'] = 'mox-agent-clubhouse-master-key-2026'
sys.path.insert(0, '/home/sblanken/workspace/MR-Krabs')

DIR = '/home/sblanken/workspace/mrkrabs-challenge-2-llm-gateway'
spec = open(os.path.join(DIR, 'SPEC.md')).read()

from src.core.orchestrator import LLMOrchestrator
orch = LLMOrchestrator()
start = time.monotonic()

result = orch.execute_with_judge(
    task_id='c2-gateway-v4',
    context={
        'task_spec': spec,
        '_multi_pass_child': True,
        'files': ['gateway.py', 'test_gateway.py'],
        'spec': {
            'success_criteria': [
                'All 8 pytest tests pass',
                'Zero external dependencies beyond stdlib',
                'SSE streaming works end-to-end',
                'Primary-to-secondary failover on mid-stream failure',
                'Unsupported parameter stripping works',
                'Telemetry logs all required fields',
            ],
            'constraints': [
                'Python stdlib only — no flask, fastapi, aiohttp, requests, httpx',
                'Use http.server.HTTPServer for the proxy server',
                'Backend communication via urllib.request',
            ],
        },
    },
    tiers=['l0-coder', 'l1-coder', 'l2-coder', 'principal'],
    max_retries_per_tier=3, judge_model='judge',
    project_root=DIR, timeout_seconds=2400,
)

elapsed = time.monotonic() - start
print(f"\n=== C2 RESULT: success={result.get('success')}, tier={result.get('tier_used')}, "
      f"retries={result.get('retries',0)}, score={result.get('judge_score')}, "
      f"duration={elapsed:.0f}s")

files = result.get('files', {})
for p in sorted(files.keys()):
    print(f"  {p} ({len(files[p])} bytes)")

with open(os.path.join(DIR, 'mrkrabs_result.json'), 'w') as f:
    json.dump({'challenge':'c2','success':result.get('success'),
        'tier':str(result.get('tier_used','')),'retries':result.get('retries',0),
        'score':result.get('judge_score'),'elapsed_s':elapsed,
        'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, default=str)

tr = subprocess.run(['python3','-m','pytest','test_gateway.py','-v','--tb=short'],
    cwd=DIR, capture_output=True, text=True, timeout=120)
print(f"\nTests: {tr.stdout.count('PASSED')} passed, {tr.stdout.count('FAILED')} failed, exit={tr.returncode}")
if tr.returncode != 0:
    print(tr.stdout[-1500:])
