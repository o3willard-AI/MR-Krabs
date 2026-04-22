#!/usr/bin/env python3
"""Hello world example for cost-optimized orchestration.

Usage:
    export OPENROUTER_API_KEY="your-key"
    python examples/hello_world.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.cost import CostTracker, Budget, TokenCount
from src.core.model_capabilities import CapabilityChecker


def main():
    print("Cost-Optimized Orchestrator — Hello World")
    print("=" * 50)
    print()

    # Show budget configuration
    tracker = CostTracker(budget=Budget(daily_limit_usd=10.0))
    summary = tracker.get_summary()
    print(f"Budget: ${summary['budget_limit']:.2f}/day")
    print(f"Remaining: ${summary['budget_remaining']:.2f}")
    print()

    # Show model capabilities
    checker = CapabilityChecker()
    print("Available models:")
    capable = checker.find_capable_models(prefer_free=True)
    for model_id in capable[:5]:
        cap = checker._registry[model_id]
        print(f"  {model_id}")
        print(f"    Context: {cap.context_window:,} tokens")
        print(f"    Tools: {'Yes' if cap.supports_tool_calling else 'No'}")
        print(f"    Free: {'Yes' if cap.is_free_tier else 'No'}")
    print()

    print("To execute a task:")
    print('  from cost_orchestrator import ask')
    print('  result = ask("Write a hello world in Python")')
    print(f'  print(f"Cost: ${{result.cost:.4f}}")')


if __name__ == "__main__":
    main()
