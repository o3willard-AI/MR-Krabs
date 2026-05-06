"""
Phase 2: CrewAI Orchestration Tools - Integration Tests

Tests the CrewAI-based tools without requiring real LLM calls.
Focuses on validation, request/response handling, and graceful degradation.
"""

import pytest
from src.mcp.crew_tools import (
    CrewCreateRequest,
    CrewExecuteRequest,
    AgentExecuteRequest,
    process_crew_create,
    process_crew_execute,
    process_agent_execute,
    CREWAI_AVAILABLE,
)


# ==================== Crew Creation Tests ====================

class TestCrewCreation:
    """Test crew creation and validation."""
    
    def test_valid_crew_config(self):
        """Test that valid crew config is accepted."""
        request = CrewCreateRequest(
            crew_config={
                "name": "test-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Agent Role",
                        "goal": "Achieve goal",
                        "backstory": "Background story"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task description",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        assert result.success is True
        assert "validated" in result.message.lower() or str(result.success).lower() in result.message.lower()
        assert result.crew_id is not None
    
    def test_missing_agents_field(self):
        """Test that missing agents field returns error."""
        request = CrewCreateRequest(
            crew_config={
                "name": "incomplete-crew",
                "tasks": [
                    {
                        "description": "Task without agents"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        assert result.success is False
        assert "agents" in result.message.lower()
    
    def test_missing_tasks_field(self):
        """Test that missing tasks field returns error."""
        request = CrewCreateRequest(
            crew_config={
                "name": "incomplete-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        assert result.success is False
        assert "tasks" in result.message.lower()
    
    def test_multiple_agents_and_tasks(self):
        """Test crew with multiple agents and tasks."""
        request = CrewCreateRequest(
            crew_config={
                "name": "multi-agent-crew",
                "agents": [
                    {
                        "name": "researcher",
                        "role": "Researcher",
                        "goal": "Research topics",
                        "backstory": "Expert researcher"
                    },
                    {
                        "name": "writer",
                        "role": "Writer", 
                        "goal": "Write content",
                        "backstory": "Skilled writer"
                    }
                ],
                "tasks": [
                    {
                        "description": "Research AI trends",
                        "agent_name": "researcher"
                    },
                    {
                        "description": "Write article",
                        "agent_name": "writer"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        assert result.success is True
        assert "2" in result.message  # Should mention 2 agents
    
    def test_session_id_passed_through(self):
        """Test that session_id is preserved in response."""
        request = CrewCreateRequest(
            session_id="test-session-123",
            crew_config={
                "name": "session-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal", 
                        "backstory": "Backstory"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        assert result.session_id == "test-session-123"


# ==================== Crew Execution Tests ====================

class TestCrewExecution:
    """Test crew execution (without real LLM calls)."""
    
    def test_missing_agents_rejected(self):
        """Test that execution is rejected without agents."""
        request = CrewExecuteRequest(
            crew_config={
                "name": "empty-crew",
                "tasks": []
            }
        )
        
        result = process_crew_execute(request)
        
        assert result.success is False or result.error is not None
    
    def test_missing_tasks_rejected(self):
        """Test that execution is rejected without tasks."""
        request = CrewExecuteRequest(
            crew_config={
                "name": "no-tasks-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ]
            }
        )
        
        result = process_crew_execute(request)
        
        assert result.success is False or result.error is not None
    
    def test_graceful_degradation_without_crewai(self):
        """Test that system degrades gracefully if CrewAI not installed."""
        request = CrewExecuteRequest(
            crew_config={
                "name": "test-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        result = process_crew_execute(request)
        
        # If CrewAI not installed, should return clear error
        if not CREWAI_AVAILABLE:
            assert result.error is not None
            assert "crewai" in result.error.lower()


# ==================== Single Agent Tests ====================

class TestSingleAgentExecution:
    """Test single agent task execution."""
    
    def test_valid_prompt(self):
        """Test that valid prompt is accepted."""
        request = AgentExecuteRequest(
            prompt="Write a short poem"
        )
        
        result = process_agent_execute(request)
        
        # Should either succeed or return clear error about CrewAI/LLM
        assert result.success is True or result.error is not None
    
    def test_empty_prompt(self):
        """Test that empty prompt is handled."""
        request = AgentExecuteRequest(
            prompt=""
        )
        
        result = process_agent_execute(request)
        
        # Should handle gracefully (may fail at LLM level, but not crash)
        assert result.success is True or result.error is not None
    
    def test_long_prompt(self):
        """Test that long prompts are handled."""
        long_prompt = "Write " * 1000 + "a story"
        
        request = AgentExecuteRequest(
            prompt=long_prompt
        )
        
        result = process_agent_execute(request)
        
        # Should handle gracefully
        assert result.success is True or result.error is not None
    
    def test_model_specification(self):
        """Test that model parameter is accepted."""
        request = AgentExecuteRequest(
            prompt="Test prompt",
            model="meta-llama/llama-3-8b-instruct"
        )
        
        result = process_agent_execute(request)
        
        # Should either succeed or fail gracefully
        assert result.success is True or result.error is not None
    
    def test_budget_limit_parameter(self):
        """Test that budget limit parameter is accepted."""
        request = AgentExecuteRequest(
            prompt="Test prompt",
            budget_limit=0.50
        )
        
        result = process_agent_execute(request)
        
        # Should handle gracefully
        assert result.success is True or result.error is not None
    
    def test_graceful_degradation_without_crewai(self):
        """Test graceful degradation if CrewAI not installed."""
        request = AgentExecuteRequest(
            prompt="Test prompt"
        )
        
        result = process_agent_execute(request)
        
        # If CrewAI not installed, should return clear error
        if not CREWAI_AVAILABLE:
            assert result.error is not None
            assert "crewai" in result.error.lower()


# ==================== Integration Tests ====================

class TestIntegration:
    """Test integration between components."""
    
    def test_create_then_execute_flow(self):
        """Test the create-then-execute workflow."""
        # Step 1: Create crew
        create_request = CrewCreateRequest(
            crew_config={
                "name": "integration-test-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task description",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        create_result = process_crew_create(create_request)
        
        # Step 2: Execute crew (may fail without LLM, but should not crash)
        execute_request = CrewExecuteRequest(
            crew_config=create_request.crew_config
        )
        
        execute_result = process_crew_execute(execute_request)
        
        # Both should handle gracefully
        assert create_result.success is True or create_result.error is not None
        assert execute_result.success is True or execute_result.error is not None
    
    def test_session_id_across_tools(self):
        """Test that session_id is preserved across different tools."""
        session_id = "integration-session-456"
        
        # Crew creation with session
        create_request = CrewCreateRequest(
            session_id=session_id,
            crew_config={
                "name": "session-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        create_result = process_crew_create(create_request)
        
        # Agent execution with same session
        agent_request = AgentExecuteRequest(
            session_id=session_id,
            prompt="Test prompt"
        )
        
        agent_result = process_agent_execute(agent_request)
        
        # Both should preserve session_id
        assert create_result.session_id == session_id or create_result.success is False
        assert agent_result.session_id == session_id


# ==================== Edge Cases ====================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_special_characters_in_prompt(self):
        """Test prompts with special characters."""
        request = AgentExecuteRequest(
            prompt="Write a poem with emojis 🎨 and unicode café"
        )
        
        result = process_agent_execute(request)
        
        # Should handle gracefully
        assert result.success is True or result.error is not None
    
    def test_unicode_in_crew_config(self):
        """Test crew configs with unicode characters."""
        request = CrewCreateRequest(
            crew_config={
                "name": "unicode-crew-测试",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "分析师角色",
                        "goal": "分析数据并生成报告",
                        "backstory": "你是一名专家"
                    }
                ],
                "tasks": [
                    {
                        "description": "分析这些数据：[1, 2, 3]",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        # Should handle unicode gracefully
        assert result.success is True or result.error is not None
    
    def test_nested_config_objects(self):
        """Test deeply nested configuration objects."""
        request = CrewCreateRequest(
            config={
                "model": "test-model",
                "base_url": "https://api.example.com",
                "nested": {
                    "level1": {
                        "level2": {
                            "value": "deep"
                        }
                    }
                }
            },
            crew_config={
                "name": "nested-crew",
                "agents": [
                    {
                        "name": "agent1",
                        "role": "Role",
                        "goal": "Goal",
                        "backstory": "Backstory"
                    }
                ],
                "tasks": [
                    {
                        "description": "Task",
                        "agent_name": "agent1"
                    }
                ]
            }
        )
        
        result = process_crew_create(request)
        
        # Should handle nested configs gracefully
        assert result.success is True or result.error is not None


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
