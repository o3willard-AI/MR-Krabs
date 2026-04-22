#!/usr/bin/env python3
"""Test that the prototype imports work correctly."""

import sys
from pathlib import Path

# Add prototype directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from skills.cost_optimized_orchestration.orchestrator import (
        CostOptimizedOrchestrator, TierConfig, ExecutionResult
    )
    print("✓ Successfully imported CostOptimizedOrchestrator")
    
    # Test basic instantiation
    orchestrator = CostOptimizedOrchestrator(budget_daily_usd=10.0)
    print("✓ Successfully created orchestrator instance")
    print(f"  - Tiers configured: {len(orchestrator.tiers)}")
    print(f"  - Budget: ${orchestrator.budget_daily_usd:.2f}")
    
    # Test tier configuration
    tier_names = list(orchestrator.tiers.keys())
    print(f"  - Tier names: {', '.join(tier_names[:3])}...")
    
    # Test execution result dataclass
    result = ExecutionResult(
        task_id="test_task",
        tier="L0-Coder",
        success=True,
        output="Test output",
        cost_usd=0.001
    )
    print(f"✓ Successfully created ExecutionResult: {result.task_id}")
    
    print("\nAll imports and basic functionality work correctly!")
    sys.exit(0)
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)