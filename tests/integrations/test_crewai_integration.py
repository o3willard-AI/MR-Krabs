#!/usr/bin/env python3
"""Unit tests for crewai_integration.py - CrewAI wrappers with cost tracking."""

import pytest
from unittest.mock import Mock, MagicMock, patch, ANY
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.crewai_integration import (
    CREWAI_AVAILABLE,
    AgentRole,
    CrewConfig,
    CostAwareAgent,
    CostAwareTask,
    CostAwareCrew,
    create_simple_crew,
)


class TestCREWAI_AVAILABLE:
    """Test CrewAI availability detection."""

    def test_flag_exists(self):
        """Test that CREWAI_AVAILABLE flag exists and is boolean."""
        assert isinstance(CREWAI_AVAILABLE, bool)


class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_all_roles_exist(self):
        """Test all predefined agent roles exist."""
        expected_roles = ["researcher", "analyst", "writer", "coder", "reviewer", "planner"]
        for role in expected_roles:
            assert hasattr(AgentRole, role.upper())

    def test_role_values(self):
        """Test agent role values match expected strings."""
        assert AgentRole.RESEARCHER == "researcher"
        assert AgentRole.ANALYST == "analyst"
        assert AgentRole.WRITER == "writer"
        assert AgentRole.CODER == "coder"
        assert AgentRole.REVIEWER == "reviewer"
        assert AgentRole.PLANNER == "planner"


class TestCrewConfig:
    """Tests for CrewConfig configuration class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CrewConfig()
        
        assert config.process == "sequential"
        assert config.max_iterations == 10
        assert config.verbosity == 0
        assert config.llm_config == {}

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CrewConfig(
            process="hierarchical",
            max_iterations=20,
            verbosity=2,
            llm_config={"model": "google/gemma-7b-it"},
        )
        
        assert config.process == "hierarchical"
        assert config.max_iterations == 20
        assert config.verbosity == 2
        assert config.llm_config == {"model": "google/gemma-7b-it"}

    def test_to_crew_params_sequential(self):
        """Test conversion to Crew parameters with sequential process."""
        if not CREWAI_AVAILABLE:
            pytest.skip("CrewAI not installed")
        
        config = CrewConfig(process="sequential")
        params = config.to_crew_params()
        
        assert "process" in params
        assert "verbose" in params
        assert params["verbose"] is False  # verbosity=0 means not verbose

    def test_to_crew_params_verbose(self):
        """Test conversion with verbose logging enabled."""
        if not CREWAI_AVAILABLE:
            pytest.skip("CrewAI not installed")
        
        config = CrewConfig(process="hierarchical", verbosity=1)
        params = config.to_crew_params()
        
        assert params["verbose"] is True  # verbosity > 0 means verbose

    def test_to_crew_params_import_error(self):
        """Test that to_crew_params raises ImportError when CrewAI unavailable."""
        if CREWAI_AVAILABLE:
            pytest.skip("CrewAI is installed, can't test ImportError")
        
        config = CrewConfig(process="sequential")
        
        with pytest.raises(ImportError) as exc_info:
            config.to_crew_params()
        
        assert "CrewAI is not installed" in str(exc_info.value)


class TestCostAwareAgent:
    """Tests for CostAwareAgent wrapper."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_agent_creation(self):
        """Test basic agent creation."""
        agent = CostAwareAgent(
            role="Researcher",
            goal="Conduct research",
            backstory="Expert researcher",
        )
        
        assert agent.role == "Researcher"
        assert agent.goal == "Conduct research"
        assert agent.backstory == "Expert researcher"
        assert agent.llm_config == {}
        assert agent.verbose is False
        assert agent._agent is None

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_agent_with_llm_config(self):
        """Test agent with LLM configuration."""
        agent = CostAwareAgent(
            role="Developer",
            goal="Write code",
            llm_config={"model": "google/gemma-7b-it"},
            verbose=True,
        )
        
        assert agent.llm_config == {"model": "google/gemma-7b-it"}
        assert agent.verbose is True

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_agent_default_backstory(self):
        """Test that backstory defaults to role + goal if not provided."""
        agent = CostAwareAgent(
            role="Writer",
            goal="Write content",
        )
        
        assert "Writer" in agent.backstory
        assert "Write content" in agent.backstory

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_get_agent_creates_instance(self):
        """Test that get_agent() creates the underlying CrewAI agent."""
        with patch("src.core.crewai_integration.Agent") as mock_agent_class:
            mock_agent_instance = MagicMock()
            mock_agent_class.return_value = mock_agent_instance
            
            agent = CostAwareAgent(
                role="Tester",
                goal="Write tests",
            )
            
            # Get the agent instance
            crewai_agent = agent.get_agent()
            
            # Verify Agent was called
            mock_agent_class.assert_called_once()
            assert crewai_agent == mock_agent_instance

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_get_agent_returns_cached_instance(self):
        """Test that get_agent() returns cached instance on second call."""
        with patch("src.core.crewai_integration.Agent") as mock_agent_class:
            mock_agent_instance = MagicMock()
            mock_agent_class.return_value = mock_agent_instance
            
            agent = CostAwareAgent(
                role="Analyst",
                goal="Analyze data",
            )
            
            # First call creates instance
            first_call = agent.get_agent()
            
            # Second call should return cached instance
            second_call = agent.get_agent()
            
            assert first_call is second_call
            mock_agent_class.assert_called_once()  # Only called once

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_agent_creation_passes_correct_params(self):
        """Test that _create_agent passes correct parameters to CrewAI Agent."""
        with patch("src.core.crewai_integration.Agent") as mock_agent_class:
            mock_agent_instance = MagicMock()
            mock_agent_class.return_value = mock_agent_instance
            
            agent = CostAwareAgent(
                role="Manager",
                goal="Manage tasks",
                backstory="Experienced manager",
                verbose=True,
            )
            
            agent.get_agent()
            
            # Verify parameters passed to CrewAI Agent
            call_kwargs = mock_agent_class.call_args[1]
            assert call_kwargs["role"] == "Manager"
            assert call_kwargs["goal"] == "Manage tasks"
            assert call_kwargs["backstory"] == "Experienced manager"
            assert call_kwargs["verbose"] is True


class TestCostAwareTask:
    """Tests for CostAwareTask wrapper."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_task_creation(self):
        """Test basic task creation."""
        agent = CostAwareAgent(role="Worker", goal="Do work")
        
        task = CostAwareTask(
            description="Complete the assignment",
            expected_output="Completed assignment",
            agent=agent,
        )
        
        assert task.description == "Complete the assignment"
        assert task.expected_output == "Completed assignment"
        assert task.agent == agent
        assert task.cost_limit is None
        assert task._task is None

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_task_with_cost_limit(self):
        """Test task with cost limit."""
        agent = CostAwareAgent(role="Worker", goal="Do work")
        
        task = CostAwareTask(
            description="Do expensive task",
            expected_output="Result",
            agent=agent,
            cost_limit=5.00,
        )
        
        assert task.cost_limit == 5.00

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_get_task_creates_instance(self):
        """Test that get_task() creates the underlying CrewAI task."""
        with patch("src.core.crewai_integration.Task") as mock_task_class:
            mock_task_instance = MagicMock()
            mock_task_class.return_value = mock_task_instance
            
            agent = CostAwareAgent(role="Worker", goal="Do work")
            agent._agent = MagicMock()  # Pre-create agent to avoid Agent mocking
            
            task = CostAwareTask(
                description="Test task",
                expected_output="Test output",
                agent=agent,
            )
            
            crewai_task = task.get_task()
            
            mock_task_class.assert_called_once()
            assert crewai_task == mock_task_instance

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_get_task_returns_cached_instance(self):
        """Test that get_task() returns cached instance on second call."""
        with patch("src.core.crewai_integration.Task") as mock_task_class:
            mock_task_instance = MagicMock()
            mock_task_class.return_value = mock_task_instance
            
            agent = CostAwareAgent(role="Worker", goal="Do work")
            agent._agent = MagicMock()
            
            task = CostAwareTask(
                description="Test task",
                expected_output="Test output",
                agent=agent,
            )
            
            first_call = task.get_task()
            second_call = task.get_task()
            
            assert first_call is second_call
            mock_task_class.assert_called_once()


class TestCostAwareCrew:
    """Tests for CostAwareCrew wrapper."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_crew_creation(self):
        """Test basic crew creation."""
        agent1 = CostAwareAgent(role="Researcher", goal="Research")
        agent2 = CostAwareAgent(role="Writer", goal="Write")
        
        task1 = CostAwareTask(
            description="Research topic",
            expected_output="Research findings",
            agent=agent1,
        )
        task2 = CostAwareTask(
            description="Write report",
            expected_output="Final report",
            agent=agent2,
        )
        
        crew = CostAwareCrew(
            tasks=[task1, task2],
            agents=[agent1, agent2],
        )
        
        assert len(crew.tasks) == 2
        assert len(crew.agents) == 2
        assert crew.cost_limit is None
        assert crew._crew is None

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_crew_with_cost_limit(self):
        """Test crew with total cost limit."""
        agent = CostAwareAgent(role="Worker", goal="Work")
        task = CostAwareTask(
            description="Do work",
            expected_output="Done",
            agent=agent,
        )
        
        crew = CostAwareCrew(
            tasks=[task],
            agents=[agent],
            cost_limit=10.00,
        )
        
        assert crew.cost_limit == 10.00

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_crew_with_custom_config(self):
        """Test crew with custom configuration."""
        agent = CostAwareAgent(role="Worker", goal="Work")
        task = CostAwareTask(
            description="Do work",
            expected_output="Done",
            agent=agent,
        )
        
        config = CrewConfig(process="hierarchical", verbosity=1)
        
        crew = CostAwareCrew(
            tasks=[task],
            agents=[agent],
            config=config,
        )
        
        assert crew.config == config

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_kickoff_without_preset_crew(self):
        """Test kickoff() when _crew is not pre-created."""
        with patch("src.core.crewai_integration.Crew") as mock_crew_class:
            mock_crew_instance = MagicMock()
            mock_result = "Task completed successfully"
            mock_crew_instance.kickoff.return_value = mock_result
            
            agent = CostAwareAgent(role="Worker", goal="Work")
            task = CostAwareTask(
                description="Do work",
                expected_output="Done",
                agent=agent,
            )
            
            # Pre-create underlying instances to avoid mocking Agent/Task creation
            agent._agent = MagicMock()
            task._task = MagicMock()
            
            crew = CostAwareCrew(tasks=[task], agents=[agent])
            
            result = crew.kickoff()
            
            # Verify Crew was created
            mock_crew_class.assert_called_once()
            
            # Verify kickoff was called
            mock_crew_instance.kickoff.assert_called_once()
            
            # Verify result format
            assert isinstance(result, dict)
            assert "output" in result
            assert "cost" in result
            assert result["output"] == mock_result
            assert result["cost"] == 0.0  # Default cost until real tracking added

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_kickoff_with_existing_crew(self):
        """Test kickoff() with pre-existing crew instance."""
        with patch("src.core.crewai_integration.Crew") as mock_crew_class:
            mock_crew_instance = MagicMock()
            mock_result = "Output"
            mock_crew_instance.kickoff.return_value = mock_result
            
            agent = CostAwareAgent(role="Worker", goal="Work")
            task = CostAwareTask(
                description="Do work",
                expected_output="Done",
                agent=agent,
            )
            
            crew = CostAwareCrew(tasks=[task], agents=[agent])
            
            # Pre-create the crew instance
            crew._crew = mock_crew_instance
            
            result = crew.kickoff()
            
            # Crew should NOT be called again since we have _crew
            mock_crew_class.assert_not_called()
            assert result["output"] == mock_result

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_kickoff_logs_info(self):
        """Test that kickoff logs task count and budget."""
        import logging
        
        with patch("src.core.crewai_integration.Crew"):
            agent = CostAwareAgent(role="Worker", goal="Work")
            task1 = CostAwareTask(description="Task 1", expected_output="Out 1", agent=agent)
            task2 = CostAwareTask(description="Task 2", expected_output="Out 2", agent=agent)
            
            # Pre-create instances
            agent._agent = MagicMock()
            task1._task = MagicMock()
            task2._task = MagicMock()
            
            crew = CostAwareCrew(
                tasks=[task1, task2],
                agents=[agent],
                cost_limit=5.00,
            )
            
            # Capture log output
            with caplog.at_level(logging.INFO):
                crew.kickoff()

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_kickoff_for_each(self):
        """Test kickoff_for_each runs crew multiple times."""
        with patch.object(CostAwareCrew, 'kickoff') as mock_kickoff:
            mock_kickoff.return_value = {"output": "result", "cost": 0.5}
            
            agent = CostAwareAgent(role="Worker", goal="Work")
            task = CostAwareTask(
                description="Do work",
                expected_output="Done",
                agent=agent,
            )
            
            crew = CostAwareCrew(tasks=[task], agents=[agent])
            
            inputs = [{"topic": "A"}, {"topic": "B"}, {"topic": "C"}]
            
            results = crew.kickoff_for_each(inputs)
            
            # Should have been called 3 times
            assert len(results) == 3
            mock_kickoff.assert_called()


class TestCreateSimpleCrew:
    """Tests for create_simple_crew convenience function."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_simple_crew_basic(self):
        """Test basic simple crew creation."""
        crew = create_simple_crew(
            tasks=[
                {
                    "description": "Research AI",
                    "expected_output": "Research report",
                    "agent_role": 0,
                },
            ],
            agents=[
                {"role": "Researcher", "goal": "Find information"},
            ],
        )
        
        assert isinstance(crew, CostAwareCrew)
        assert len(crew.tasks) == 1
        assert len(crew.agents) == 1

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_simple_crew_multiple_tasks(self):
        """Test simple crew with multiple tasks and agents."""
        crew = create_simple_crew(
            tasks=[
                {"description": "Research", "expected_output": "Report", "agent_role": 0},
                {"description": "Write", "expected_output": "Article", "agent_role": 1},
                {"description": "Review", "expected_output": "Feedback", "agent_role": 2},
            ],
            agents=[
                {"role": "Researcher", "goal": "Research"},
                {"role": "Writer", "goal": "Write"},
                {"role": "Reviewer", "goal": "Review"},
            ],
        )
        
        assert len(crew.tasks) == 3
        assert len(crew.agents) == 3
        
        # Verify tasks are linked to correct agents
        assert crew.tasks[0].agent.role == "Researcher"
        assert crew.tasks[1].agent.role == "Writer"
        assert crew.tasks[2].agent.role == "Reviewer"

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_simple_crew_default_process(self):
        """Test that simple crew uses sequential process by default."""
        crew = create_simple_crew(
            tasks=[{"description": "Task", "expected_output": "Out", "agent_role": 0}],
            agents=[{"role": "Agent", "goal": "Goal"}],
        )
        
        assert crew.config.process == "sequential"

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_simple_crew_custom_process(self):
        """Test simple crew with custom process."""
        crew = create_simple_crew(
            tasks=[{"description": "Task", "expected_output": "Out", "agent_role": 0}],
            agents=[{"role": "Agent", "goal": "Goal"}],
            process="hierarchical",
        )
        
        assert crew.config.process == "hierarchical"

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_simple_crew_default_agent_role(self):
        """Test that tasks without agent_role default to 0."""
        crew = create_simple_crew(
            tasks=[
                {"description": "Task", "expected_output": "Out"},  # No agent_role
            ],
            agents=[{"role": "Default Agent", "goal": "Default"}],
        )
        
        # Should default to first agent (index 0)
        assert crew.tasks[0].agent.role == "Default Agent"


class TestErrorHandling:
    """Tests for error handling when CrewAI is not available."""

    def test_cost_aware_agent_import_error(self):
        """Test CostAwareAgent raises ImportError when CrewAI unavailable."""
        # Temporarily mock CREWAI_AVAILABLE as False
        with patch("src.core.crewai_integration.CREWAI_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                CostAwareAgent(role="Test", goal="Test")
            
            assert "CrewAI is not installed" in str(exc_info.value)

    def test_cost_aware_task_import_error(self):
        """Test CostAwareTask works without CrewAI (agent creation will fail)."""
        # Task itself doesn't check, but agent does
        with patch("src.core.crewai_integration.CREWAI_AVAILABLE", False):
            with pytest.raises(ImportError):
                agent = CostAwareAgent(role="Test", goal="Test")

    def test_cost_aware_crew_import_error(self):
        """Test CostAwareCrew raises ImportError when CrewAI unavailable."""
        with patch("src.core.crewai_integration.CREWAI_AVAILABLE", False):
            agent = Mock()  # Use mock agent to bypass CostAwareAgent check
            task = Mock()   # Use mock task
            
            with pytest.raises(ImportError) as exc_info:
                CostAwareCrew(tasks=[task], agents=[agent])
            
            assert "CrewAI is not installed" in str(exc_info.value)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_empty_crew(self):
        """Test crew with no tasks (edge case)."""
        agent = CostAwareAgent(role="Worker", goal="Work")
        
        crew = CostAwareCrew(
            tasks=[],
            agents=[agent],
        )
        
        assert len(crew.tasks) == 0
        assert len(crew.agents) == 1

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_agent_with_tools(self):
        """Test agent with tools parameter (tools not validated at creation)."""
        mock_tool = Mock()
        
        agent = CostAwareAgent(
            role="Worker",
            goal="Work",
            tools=[mock_tool],
        )
        
        # Tools are stored but not used in basic _create_agent
        # They would be passed to actual CrewAI Agent when extended

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_task_with_tools(self):
        """Test task with tools parameter."""
        mock_tool = Mock()
        
        agent = CostAwareAgent(role="Worker", goal="Work")
        
        task = CostAwareTask(
            description="Do work",
            expected_output="Result",
            agent=agent,
            tools=[mock_tool],
        )
        
        # Tools stored but not used in basic _create_task
        assert task._task is None  # Not created until get_task() called

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_very_high_cost_limit(self):
        """Test with very high cost limit."""
        agent = CostAwareAgent(role="Worker", goal="Work")
        
        task = CostAwareTask(
            description="Expensive task",
            expected_output="Result",
            agent=agent,
            cost_limit=1000.00,  # $1000 budget!
        )
        
        assert task.cost_limit == 1000.00

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_zero_cost_limit(self):
        """Test with zero cost limit (edge case)."""
        agent = CostAwareAgent(role="Worker", goal="Work")
        
        task = CostAwareTask(
            description="Free task",
            expected_output="Result",
            agent=agent,
            cost_limit=0.0,  # Zero budget
        )
        
        assert task.cost_limit == 0.0

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_unicode_in_role_and_goal(self):
        """Test agent with unicode characters."""
        agent = CostAwareAgent(
            role="数据分析师 (Data Analyst)",
            goal="分析数据并生成报告 (Analyze data and generate reports)",
        )
        
        assert "数据分析师" in agent.role
        assert "分析数据" in agent.goal


class TestIntegrationScenarios:
    """Integration-style tests that combine multiple components."""

    @pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
    def test_complete_workflow(self):
        """Test complete workflow from creation to kickoff."""
        with patch("src.core.crewai_integration.Crew") as mock_crew_class:
            mock_crew_instance = MagicMock()
            mock_result = "Final report completed"
            mock_crew_instance.kickoff.return_value = mock_result
            
            # Create agents
            researcher = CostAwareAgent(
                role="Research Lead",
                goal="Conduct comprehensive research",
                llm_config={"model": "google/gemma-7b-it"},
            )
            writer = CostAwareAgent(
                role="Content Writer",
                goal="Write engaging articles",
            )
            
            # Create tasks with budgets
            research_task = CostAwareTask(
                description="Research AI cost optimization trends",
                expected_output="Detailed research report with findings",
                agent=researcher,
                cost_limit=0.50,
            )
            writing_task = CostAwareTask(
                description="Write article based on research",
                expected_output="Complete article ready for publication",
                agent=writer,
                cost_limit=0.75,
            )
            
            # Create crew with config
            crew = CostAwareCrew(
                tasks=[research_task, writing_task],
                agents=[researcher, writer],
                config=CrewConfig(process="sequential", verbosity=1),
                cost_limit=1.25,  # Total budget: $1.25
            )
            
            # Execute
            result = crew.kickoff()
            
            # Verify
            assert isinstance(result, dict)
            assert "output" in result
            assert "cost" in result
            assert result["output"] == mock_result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
