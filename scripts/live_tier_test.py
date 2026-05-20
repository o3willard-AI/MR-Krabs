#!/usr/bin/env python3
"""Live tier escalation integration test for MR-Krabs."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OPENROUTER_API_KEY"] = open("/home/ubuntu/.openrouter-key").read().strip()

from src.core.model_config import MODELS
original_url = MODELS["L0-Coder"]["base_url"]

# Force L0 failure by pointing to dead endpoint
MODELS["L0-Coder"]["base_url"] = "http://127.0.0.1:1/v1"

from src import ask

print("=== Forced Escalation Test ===")
print(f"L0-Coder URL: {MODELS['L0-Coder']['base_url']}")
print(f"L1-Coder: {MODELS['L1-Coder']['model']}")
print()

result = ask("Write a Python function gcd(a,b) that returns the greatest common divisor. Return ONLY the function code.")

print(f"  Tier used:    {result.tier}")
print(f"  Model:        {result.model}")
print(f"  Cost:         ${result.cost:.6f}")
print(f"  Attempts:     {result.attempts}")
print(f"  Success:      {result.success}")
print(f"  Duration:     {result.duration_seconds:.2f}s")
if result.output:
    lines = result.output.strip().split('\n')
    print(f"  Output ({len(lines)} lines, {len(result.output)} chars):")
    for line in lines[:8]:
        print(f"    {line}")
    print()

# Restore L0
MODELS["L0-Coder"]["base_url"] = original_url
print(f"L0 restored to: {original_url}")

# Reversion test: new task with L0 available again
print()
print("=== Reversion Test (L0 available, new task) ===")
result2 = ask("Write a Python function is_prime(n). Return ONLY the function.")
print(f"  Tier used:    {result2.tier}")
print(f"  Model:        {result2.model}")
print(f"  Cost:         ${result2.cost:.6f}")
print(f"  Success:      {result2.success}")
if result2.output:
    print(f"  Output:       {result2.output.strip()[:150]}...")
