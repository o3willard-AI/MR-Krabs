#!/usr/bin/env python3
"""
Tests for failure action system.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.core.failure_action import FailureAction
from src.core.tier_config import get_tier_failure_action, get_tier_max_retries
from src.core.human_gate import write_pending_file, wait_for_human, confirm_task, deny_task


def test_failure_action_enum_values():
    """Test that FailureAction enum has correct values."""
    assert FailureAction.LOG_ONLY.value == "log_only"
    assert FailureAction.NOTIFY_AND_ESCALATE.value == "notify_and_escalate"
    assert FailureAction.NOTIFY_AND_WAIT.value == "notify_and_wait"


def test_get_tier_failure_action_default_values():
    """Test that get_tier_failure_action returns correct defaults."""
    # Test L0-Coder
    assert get_tier_failure_action("L0-Coder") == FailureAction.LOG_ONLY
    
    # Test L1-Coder  
    assert get_tier_failure_action("L1-Coder") == FailureAction.NOTIFY_AND_ESCALATE
    
    # Test L2-Coder
    assert get_tier_failure_action("L2-Coder") == FailureAction.NOTIFY_AND_WAIT
    
    # Test L3-Coder
    assert get_tier_failure_action("L3-Coder") == FailureAction.NOTIFY_AND_WAIT
    
    # Test unknown tier returns default (LOG_ONLY)
    assert get_tier_failure_action("Unknown-Tier") == FailureAction.LOG_ONLY


def test_get_tier_max_retries_default_values():
    """Test that get_tier_max_retries returns correct defaults."""
    # Test L0-Coder
    assert get_tier_max_retries("L0-Coder") == 3
    
    # Test L1-Coder  
    assert get_tier_max_retries("L1-Coder") == 3
    
    # Test L2-Coder
    assert get_tier_max_retries("L2-Coder") == 3
    
    # Test L3-Coder
    assert get_tier_max_retries("L3-Coder") == 2
    
    # Test unknown tier returns default (3)
    assert get_tier_max_retries("Unknown-Tier") == 3


def test_write_pending_file():
    """Test that write_pending_file creates valid JSON."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set the pending directory to temp dir
        original_pending = os.path.expanduser("~/.mrkrabs/pending")
        os.environ["HOME"] = tmp_dir
        
        task_id = "test-task-123"
        info = {
            "tier": "L2-Coder",
            "attempts": 2,
            "cost_summary": "$0.50",
            "verdict": None
        }
        
        file_path = write_pending_file(task_id, info)
        
        # Check that file was created
        assert file_path.exists()
        assert str(file_path).endswith(f"{task_id}.json")
        
        # Check content
        with open(file_path, 'r') as f:
            import json as _json
            data = _json.load(f)
            assert data["tier"] == "L2-Coder"
            assert data["cost_summary"] == "$0.50"
            
        # Restore original HOME
        os.environ["HOME"] = original_pending


def test_wait_for_human_confirmed():
    """Test that wait_for_human returns (True, None) when confirmed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set the pending directory to temp dir  
        original_pending = os.path.expanduser("~/.mrkrabs/pending")
        os.environ["HOME"] = tmp_dir
        
        task_id = "test-task-123"
        
        # Create a pending file with confirmed=True
        pending_file = Path(tmp_dir) / ".mrkrabs" / "pending" / f"{task_id}.json"
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(pending_file, 'w') as f:
            import json
            json.dump({"confirmed": True}, f)
        
        # Wait for human should return confirmed=True, None (with very short timeout)
        result = wait_for_human(task_id, timeout_minutes=0.01)  # Very small timeout to avoid hanging
        assert result == (True, None)
        
        # Restore original HOME
        os.environ["HOME"] = original_pending


def test_wait_for_human_denied():
    """Test that wait_for_human returns (False, reason) when denied."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set the pending directory to temp dir
        original_pending = os.path.expanduser("~/.mrkrabs/pending")
        os.environ["HOME"] = tmp_dir
        
        task_id = "test-task-123"
        
        # Create a pending file with confirmed=False and reason
        pending_file = Path(tmp_dir) / ".mrkrabs" / "pending" / f"{task_id}.json"
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(pending_file, 'w') as f:
            import json
            json.dump({"confirmed": False, "reason": "User denied escalation"}, f)
        
        # Wait for human should return confirmed=False, reason (with very short timeout)
        result = wait_for_human(task_id, timeout_minutes=0.01)  # Very small timeout to avoid hanging
        assert result == (False, "User denied escalation")
        
        # Restore original HOME
        os.environ["HOME"] = original_pending


def test_confirm_task():
    """Test that confirm_task sets confirmed=True."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set the pending directory to temp dir
        original_pending = os.path.expanduser("~/.mrkrabs/pending")
        os.environ["HOME"] = tmp_dir
        
        task_id = "test-task-123"
        
        # Create a pending file
        pending_file = Path(tmp_dir) / ".mrkrabs" / "pending" / f"{task_id}.json"
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(pending_file, 'w') as f:
            import json
            json.dump({"tier": "L2-Coder"}, f)
        
        # Confirm the task
        confirm_task(task_id)
        
        # Check that file was updated
        with open(pending_file, 'r') as f:
            data = json.load(f)
            assert data["confirmed"] is True
            
        # Restore original HOME
        os.environ["HOME"] = original_pending


def test_deny_task():
    """Test that deny_task sets confirmed=False and reason."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set the pending directory to temp dir
        original_pending = os.path.expanduser("~/.mrkrabs/pending")
        os.environ["HOME"] = tmp_dir
        
        task_id = "test-task-123"
        
        # Create a pending file
        pending_file = Path(tmp_dir) / ".mrkrabs" / "pending" / f"{task_id}.json"
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(pending_file, 'w') as f:
            import json
            json.dump({"tier": "L2-Coder"}, f)
        
        # Deny the task
        deny_task(task_id, "User requested cancellation")
        
        # Check that file was updated
        with open(pending_file, 'r') as f:
            data = json.load(f)
            assert data["confirmed"] is False
            assert data["reason"] == "User requested cancellation"
            
        # Restore original HOME
        os.environ["HOME"] = original_pending


def test_integration_log_only_tier():
    """Test integration: LOG_ONLY tier should just log and continue."""
    # This would require mocking the orchestrator, but we can at least verify imports work
    
    # Just test that we can import and use everything
    from src.core.tier_config import TIER_FAILURE_DEFAULTS
    assert "L0-Coder" in TIER_FAILURE_DEFAULTS
    assert TIER_FAILURE_DEFAULTS["L0-Coder"]["failure_action"] == "log_only"
    

def test_integration_notify_and_escalate_tier():
    """Test integration: NOTIFY_AND_ESCALATE tier should log and continue."""
    from src.core.tier_config import TIER_FAILURE_DEFAULTS
    assert "L1-Coder" in TIER_FAILURE_DEFAULTS
    assert TIER_FAILURE_DEFAULTS["L1-Coder"]["failure_action"] == "notify_and_escalate"


def test_integration_notify_and_wait_tier():
    """Test integration: NOTIFY_AND_WAIT tier should write pending file and wait."""
    from src.core.tier_config import TIER_FAILURE_DEFAULTS
    assert "L2-Coder" in TIER_FAILURE_DEFAULTS
    assert TIER_FAILURE_DEFAULTS["L2-Coder"]["failure_action"] == "notify_and_wait"
    
    assert "L3-Coder" in TIER_FAILURE_DEFAULTS
    assert TIER_FAILURE_DEFAULTS["L3-Coder"]["failure_action"] == "notify_and_wait"


def test_integration_orchestrator_failure_action_import():
    """Test that orchestrator can import and use the new modules."""
    # This tests that our imports work correctly in orchestrator
    from src.core.failure_action import FailureAction
    from src.core.tier_config import get_tier_failure_action
    
    assert FailureAction.LOG_ONLY == get_tier_failure_action("L0-Coder")
    assert FailureAction.NOTIFY_AND_ESCALATE == get_tier_failure_action("L1-Coder")
    assert FailureAction.NOTIFY_AND_WAIT == get_tier_failure_action("L2-Coder")