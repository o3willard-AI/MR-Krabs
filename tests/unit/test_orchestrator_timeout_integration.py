#!/usr/bin/env python3
"""Integration tests for timeout functionality in orchestrator."""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.orchestrator import LLMOrchestrator
from src.core.timeout import TaskTimeout
from src.core.exceptions import TaskTimeoutError
from src.core.judge import Verdict


class TestOrchestratorTimeout:
    """Tests for orchestrator timeout integration."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with correct project root."""
        project_root = Path(__file__).parent.parent.parent
        return LLMOrchestrator(project_root=str(project_root))
    
    def test_orchestrator_timeout_integration(self, orchestrator):
        """Test that orchestrator respects timeout settings."""
        accept = Verdict(accepted=True, score=0.9, critique="ok", checks_passed=[], checks_failed=[])
        with patch.object(orchestrator, '_get_agent_system_prompt', return_value="mock template"), \
             patch.object(orchestrator, 'call_llm_with_retry') as mock_call, \
             patch('src.core.orchestrator.Judge.evaluate', return_value=accept):
            mock_call.side_effect = lambda *args, **kwargs: time.sleep(2) or {
                "success": True, "output": "test result",
                "attempt": 1, "duration_seconds": 2.0,
            }
            with pytest.raises(TaskTimeoutError):
                orchestrator.execute_task(
                    task_id="test_task", tier="L0-Planner",
                    context={"test": "data"}, max_task_duration_seconds=1,
                )
    
    def test_orchestrator_normal_execution(self, orchestrator):
        """Test that normal execution works without timeout."""
        accept = Verdict(accepted=True, score=0.9, critique="ok", checks_passed=[], checks_failed=[])
        with patch.object(orchestrator, '_get_agent_system_prompt', return_value="mock template"), \
             patch.object(orchestrator, 'call_llm_with_retry') as mock_call, \
             patch('src.core.orchestrator.Judge.evaluate', return_value=accept):
            mock_call.return_value = {
                "success": True, "output": "test result",
                "attempt": 1, "duration_seconds": 0.1,
            }
            result = orchestrator.execute_task(
                task_id="test_task", tier="L0-Planner",
                context={"test": "data"}, max_task_duration_seconds=10,
            )
            assert result["success"] is True
            assert result["output"] == "test result"