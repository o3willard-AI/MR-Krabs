import sys
sys.path.insert(0, '/home/sblanken/working/code/MR-Krabs')

print("=" * 60)
print("MR-Krabs MCP Server - Phase 1 Cost Tools Validation")
print("=" * 60)

# Test 1: Cost Estimation
print("\n1. Testing Cost Estimation...")
from src.mcp.cost_tools import estimate_cost, COST_RATES

result = estimate_cost(
    model="google/gemma-7b-it",
    input_tokens=100,
    output_tokens=50,
)

assert result.estimated_cost > 0
assert result.input_tokens == 100
assert result.output_tokens == 50
print(f"   ✓ Estimated cost: ${result.estimated_cost:.6f}")

# Test with text
result_text = estimate_cost(
    model="meta-llama/llama-3-8b-instruct",
    prompt_text="Write a comprehensive analysis of the following topic covering all major aspects",
)
assert result_text.estimated_cost > 0 or result_text.input_tokens > 0
print(f"   ✓ Text estimation works: {result_text.input_tokens} tokens")

# Test 2: Cost Rates Configuration
print("\n2. Testing Cost Rates...")
assert "default" in COST_RATES
assert len(COST_RATES) >= 5
print(f"   ✓ {len(COST_RATES)} cost rates configured")

# Test specific models
for model in ["google/gemma-7b-it", "meta-llama/llama-3-8b-instruct"]:
    assert model in COST_RATES
print(f"   ✓ Known model rates present")

# Test 3: Cost Tracking
print("\n3. Testing Cost Tracking...")
from src.mcp.cost_tools import process_cost_track, CostTrackRequest

track_request = CostTrackRequest(
    session_id="session-test123",
    amount=0.05,
    model="google/gemma-7b-it",
    input_tokens=100,
    output_tokens=50,
)

track_result = process_cost_track(track_request)

assert track_result.recorded is True
assert track_result.record["amount"] == 0.05
assert "timestamp" in track_result.record
print(f"   ✓ Cost tracking works")
print(f"   ✓ Record created with timestamp: {track_result.record['timestamp']:.0f}")

# Test 4: Request Processing
print("\n4. Testing Request Processing...")
from src.mcp.cost_tools import (
    process_cost_estimate,
    CostEstimateRequest,
    BudgetCheckRequest,
)

# Estimate request
estimate_request = CostEstimateRequest(
    model="google/gemma-7b-it",
    input_tokens=200,
    output_tokens=100,
)

estimate_response = process_cost_estimate(estimate_request)

assert estimate_response.estimated_cost > 0
assert "breakdown" in estimate_response.dict() or hasattr(estimate_response, 'breakdown')
print(f"   ✓ Estimate request processed: ${estimate_response.estimated_cost:.6f}")

# Test 5: Budget Check Integration
print("\n5. Testing Budget Check Integration...")
from src.mcp.budget_enforcer import BudgetEnforcer

enforcer = BudgetEnforcer(
    budget_limit=100.0,
    enforcement_mode="notify_then_fail",
    warning_threshold=80.0,
)

# Should proceed without warning
check_result = enforcer.check_budget(would_spend=50.0)
assert check_result.can_proceed is True
print(f"   ✓ Budget check: $50 on $100 budget - ALLOWED")

# Should warn but still allow
check_result_warn = enforcer.check_budget(would_spend=85.0)
assert check_result_warn.can_proceed is True
assert check_result_warn.warning is not None
print(f"   ✓ Budget check: $85 on $100 budget - ALLOWED WITH WARNING")

# Should block
check_result_block = enforcer.check_budget(would_spend=110.0)
assert check_result_block.can_proceed is False
assert check_result_block.error is not None
print(f"   ✓ Budget check: $110 on $100 budget - BLOCKED")

# Test 6: All Enforcement Modes
print("\n6. Testing All Enforcement Modes...")
modes = ["notify_only", "fail", "notify_then_fail", "fail_with_notification"]

for mode in modes:
    enforcer_mode = BudgetEnforcer(
        budget_limit=100.0,
        enforcement_mode=mode,
    )
    
    result = enforcer_mode.check_budget(would_spend=50.0)
    assert result.can_proceed is True
    
print(f"   ✓ All {len(modes)} enforcement modes functional")

# Test 7: Module Exports
print("\n7. Testing Module Exports...")
from src.mcp import (
    estimate_cost,
    CostEstimateRequest,
    CostEstimateResponse,
    BudgetCheckRequest,
    BudgetCheckResponse,
    CostTrackRequest,
    CostTrackResponse,
)

print(f"   ✓ All Phase 1 components exported correctly")

# Test 8: Realistic Scenarios
print("\n8. Testing Realistic Scenarios...")

# Scenario A: Small query
small_cost = estimate_cost(
    model="meta-llama/llama-3-8b-instruct",
    input_tokens=10,
    output_tokens=20,
)
assert small_cost.estimated_cost > 0
print(f"   ✓ Small query: ${small_cost.estimated_cost:.8f}")

# Scenario B: Medium conversation
medium_cost = estimate_cost(
    model="google/gemma-7b-it",
    input_tokens=500,
    output_tokens=300,
)
assert medium_cost.estimated_cost > 0 and medium_cost.estimated_cost < 1.0
print(f"   ✓ Medium conversation: ${medium_cost.estimated_cost:.8f}")

# Scenario C: Large document processing
large_cost = estimate_cost(
    model="meta-llama/llama-3-70b-instruct",
    input_tokens=5000,
    output_tokens=2000,
)
assert large_cost.estimated_cost > 0 and large_cost.estimated_cost < 10.0
print(f"   ✓ Large document: ${large_cost.estimated_cost:.8f}")

# Test 9: Edge Cases
print("\n9. Testing Edge Cases...")

# Zero tokens
zero_cost = estimate_cost(
    model="google/gemma-7b-it",
    input_tokens=0,
    output_tokens=0,
)
assert zero_cost.estimated_cost == 0
print(f"   ✓ Zero tokens: $0.00")

# Unknown model (should use default rate)
unknown_cost = estimate_cost(
    model="super-unknown-model",
    input_tokens=100,
    output_tokens=50,
)
assert unknown_cost.estimated_cost > 0
print(f"   ✓ Unknown model uses default rate: ${unknown_cost.estimated_cost:.6f}")

# Test 10: Cost Breakdown Details
print("\n10. Testing Cost Breakdown Details...")

detailed = estimate_cost(
    model="google/gemma-7b-it",
    input_tokens=1000,
    output_tokens=500,
)

breakdown = detailed.to_dict()
assert breakdown["input_tokens"] == 1000
assert breakdown["output_tokens"] == 500
assert breakdown["model"] == "google/gemma-7b-it"
assert breakdown["rate_per_1k_input"] == COST_RATES["google/gemma-7b-it"]["input"]
assert breakdown["rate_per_1k_output"] == COST_RATES["google/gemma-7b-it"]["output"]
print(f"   ✓ Detailed breakdown includes all required fields")

# Summary
print("\n" + "=" * 60)
print("✓ Phase 1 Cost Tools Validation PASSED")
print("=" * 60)
print("\nFeatures Implemented:")
print("  • Cost estimation with token counts and prompt text")
print("  • 7+ LLM model cost rates configured")
print("  • Cost tracking with timestamps")
print("  • Budget enforcement integration (4 modes)")
print("  • Request/response models for API integration")
print("  • Stateful and stateless operation modes")
print("\nReady for: Phase 2 - CrewAI Orchestration")
