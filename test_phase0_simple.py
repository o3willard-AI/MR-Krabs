import sys
sys.path.insert(0, '/home/sblanken/working/code/MR-Krabs')

print("=" * 60)
print("MR-Krabs MCP Server - Phase 0 Core Logic Validation")
print("=" * 60)

try:
    print("\n1. Testing SessionManager...")
    from src.mcp.session_manager import SessionManager, SessionConfig
    
    manager = SessionManager(ttl_seconds=3600)
    
    # Create session
    sid = manager.create_session({"budget_limit": 15.0, "enforcement_mode": "fail"})
    assert sid.startswith("session-")
    print(f"   ✓ Created session: {sid}")
    
    # Retrieve session
    session = manager.get_session(sid)
    assert session is not None
    assert session.budget_limit == 15.0
    assert session.enforcement_mode == "fail"
    print(f"   ✓ Retrieved config correctly")
    
    # Check TTL logic (manual check)
    assert hasattr(session, 'is_expired')
    assert session.is_expired() == False
    print(f"   ✓ TTL logic functional")
    
    # Cleanup
    manager.delete_session(sid)
    print(f"   ✓ Session cleanup works")

except Exception as e:
    print(f"   ✗ SessionManager Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\n2. Testing BudgetEnforcer...")
    from src.mcp.budget_enforcer import BudgetEnforcer, EnforcementMode
    
    # Test NOTIFY_THEN_FAIL (default)
    enforcer = BudgetEnforcer(budget_limit=100.0, enforcement_mode="notify_then_fail", warning_threshold=80.0)
    
    result = enforcer.check_budget(50.0)
    assert result.can_proceed == True
    assert result.warning is None
    print(f"   ✓ Below threshold passes without warning")
    
    result = enforcer.check_budget(85.0)
    assert result.can_proceed == True
    assert result.warning is not None
    print(f"   ✓ At 85% warns but allows")
    
    result = enforcer.check_budget(110.0)
    assert result.can_proceed == False
    assert result.error is not None
    print(f"   ✓ Over budget blocked correctly")
    
    # Test NOTIFY_ONLY mode
    enforcer_notify = BudgetEnforcer(budget_limit=100.0, enforcement_mode="notify_only")
    result = enforcer_notify.check_budget(200.0)  # Way over budget
    assert result.can_proceed == True  # Still allowed in notify mode
    print(f"   ✓ NOTIFY_ONLY allows overspending")
    
    # Test FAIL_WITH_NOTIFICATION
    enforcer_fail = BudgetEnforcer(budget_limit=100.0, enforcement_mode="fail_with_notification")
    result = enforcer_fail.check_budget(150.0)
    assert "BUDGET EXCEEDED" in result.error
    print(f"   ✓ FAIL_WITH_NOTIFICATION provides detailed error")

except Exception as e:
    print(f"   ✗ BudgetEnforcer Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3. Checking Module Exports...")
from src.mcp import SessionManager, SessionConfig, BudgetEnforcer, EnforcementMode
print(f"   ✓ All components exported from src.mcp")

print("\n" + "=" * 60)
print("✓ Phase 0 Core Logic Validation PASSED")
print("=" * 60)
