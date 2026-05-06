#!/usr/bin/env python3
"""Unit tests for CostAwareCrew cost tracking integration."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sys
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.crewai_integration import (
    CostAwareCrew,
    CostAwareTask,
    CostAwareAgent,
    CrewConfig,
    CREWAI_AVAILABLE,
)
from src.core.cost import CostTracker


@pytest.mark.skipif(not CREWAI_AVAILABLE, reason="CrewAI not installed")
class TestCostAwareCrewCostTracking:
    """Tests for CostAwareCrew cost tracking integration."""

    @pytest.fixture
    def sample_cost_tracker(self):
        """Create a fresh cost tracker for tests."""
        return CostTracker()

    @pytest.fixture
    def sample_agents(self):
        """Create sample agents for crew tests."""
        return [
            CostAwareAgent(
                role="Researcher",
                goal="Research topics thoroughly",
                backstory="Expert researcher",
            ),
            CostAwareAgent(
                role="Writer",
                goal="Write clear articles",
                backstory="Professional writer",
            ),
        ]

    @pytest.fixture
    def sample_tasks(self, sample_agents):
        """Create sample tasks for crew tests."""
        return [
            CostAwareTask(
                description="Research the topic",
                expected_output="Research findings",
                agent=sample_agents[0],
            ),
            CostAwareTask(
                description="Write the article",
                expected_output="Final article",
                agent=sample_agents[1],
            ),
        ]

    def test_crew_accepts_cost_tracker(self, sample_tasks, sample_agents):
        """Test that crew can accept a cost tracker."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
        )
        
        assert crew.cost_tracker == tracker
        assert hasattr(crew, "llm_wrapper")
        assert crew.llm_wrapper.cost_tracker == tracker

    def test_crew_creates_default_cost_tracker(self, sample_tasks, sample_agents):
        """Test that crew creates a default cost tracker if not provided."""
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
        )
        
        assert isinstance(crew.cost_tracker, CostTracker)

    def test_crew_generates_unique_task_id(self, sample_tasks, sample_agents):
        """Test that crew generates a unique task ID."""
        crew1 = CostAwareCrew(tasks=sample_tasks, agents=sample_agents)
        crew2 = CostAwareCrew(tasks=sample_tasks, agents=sample_agents)
        
        assert hasattr(crew1, "task_id")
        assert hasattr(crew2, "task_id")
        assert crew1.task_id != crew2.task_id  # Should be unique
        assert crew1.task_id.startswith("crew-")

    def test_crew_llm_wrapper_configured_correctly(self, sample_tasks, sample_agents):
        """Test that LLM wrapper is configured with crew parameters."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
            cost_limit=Decimal("5.00"),
        )
        
        assert crew.llm_wrapper.cost_tracker == tracker
        assert crew.llm_wrapper.task_id == crew.task_id
        assert crew.llm_wrapper.budget_limit == Decimal("5.00")

    def test_crew_without_budget_limit(self, sample_tasks, sample_agents):
        """Test crew creation without budget limit."""
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
        )
        
        assert crew.llm_wrapper.budget_limit is None

    def test_kickoff_returns_cost_info(self, sample_tasks, sample_agents):
        """Test that kickoff returns cost information."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
        )
        
        # Mock the actual crew execution (since we can't run real LLM calls easily)
        with patch.object(crew._create_crew(), 'kickoff', return_value="mock output"):
            result = crew.kickoff()
            
        assert "output" in result
        assert "cost" in result
        assert "tokens" in result
        assert "task_id" in result

    def test_kickoff_includes_real_cost(self, sample_tasks, sample_agents):
        """Test that kickoff includes actual tracked cost."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
        )
        
        # Mock the crew execution to return output and simulate LLM calls
        with patch.object(crew._create_crew(), 'kickoff', return_value="mock output") as mock_kickoff:
            # Simulate recording a completion during execution
            crew.llm_wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
            
            result = crew.kickoff()
        
        assert result["cost"] > 0  # Should have recorded cost
        assert result["tokens"]["total"] == 150

    def test_kickoff_with_budget_limit(self, sample_tasks, sample_agents):
        """Test kickoff with budget limit."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
            cost_limit=5.0,
        )
        
        # Mock execution
        with patch.object(crew._create_crew(), 'kickoff', return_value="mock output"):
            result = crew.kickoff()
            
        assert result.get("budget_limit") == 5.0

    def test_kickoff_on_failure_still_returns_cost(self, sample_tasks, sample_agents):
        """Test that kickoff returns cost info even on failure."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
        )
        
        # Simulate recording some cost before failure
        crew.llm_wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        
        # Mock execution to raise error
        with patch.object(crew._create_crew(), 'kickoff', side_effect=Exception("Test error")):
            result = crew.kickoff()
        
        assert result["output"] is None
        assert result.get("error") is not None
        assert result["cost"] > 0  # Should still have cost info


class TestCostAwareCrewBudgetEnforcement:
    """Tests for budget enforcement in CostAwareCrew."""

    @pytest.fixture
    def minimal_tasks_and_agents(self):
        """Create minimal tasks and agents for testing."""
        agent = CostAwareAgent(
            role="Tester",
            goal="Test budget enforcement",
        )
        task = CostAwareTask(
            description="Simple test",
            expected_output="Result",
            agent=agent,
        )
        return [task], [agent]

    def test_budget_exceeded_raises_error(self, minimal_tasks_and_agents):
        """Test that exceeding budget raises BudgetExceededError."""
        from src.core.cost import BudgetExceededError
        
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=minimal_tasks_and_agents[0],
            agents=minimal_tasks_and_agents[1],
            cost_tracker=tracker,
            cost_limit=Decimal("0"),  # Zero budget - should fail immediately
        )
        
        # Try to record a completion (this simulates what would happen during kickoff)
        with pytest.raises(BudgetExceededError):
            crew.llm_wrapper.record_completion(prompt_tokens=10, completion_tokens=5)

    def test_budget_enforced_before_execution(self, minimal_tasks_and_agents):
        """Test that budget is checked before recording."""
        from src.core.cost import BudgetExceededError
        
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=minimal_tasks_and_agents[0],
            agents=minimal_tasks_and_agents[1],
            cost_tracker=tracker,
            cost_limit=Decimal("0.0000001"),  # Tiny budget
        )
        
        # Any significant LLM call should exceed this
        with pytest.raises(BudgetExceededError):
            crew.llm_wrapper.record_completion(
                prompt_tokens=100,
                completion_tokens=50,
            )


class TestCostAwareCrewIntegration:
    """Integration tests combining crew cost tracking with CostTracker."""

    def test_multiple_crews_share_tracker(self, sample_tasks, sample_agents):
        """Test that multiple crews can share the same CostTracker."""
        tracker = CostTracker()
        
        crew1 = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
            cost_limit=Decimal("5.00"),
        )
        
        crew2 = CostAwareCrew(
            tasks=sample_tasks[:1],  # Just first task
            agents=sample_agents[:1],  # Just first agent
            cost_tracker=tracker,
            cost_limit=Decimal("3.00"),
        )
        
        # Simulate some usage from each crew
        crew1.llm_wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        crew2.llm_wrapper.record_completion(prompt_tokens=200, completion_tokens=100)
        
        # Tracker should have both
        assert len(tracker.entries) == 2
        
        # Task IDs should be different
        assert crew1.task_id != crew2.task_id

    def test_crew_totals_aggregate_correctly(self, sample_tasks, sample_agents):
        """Test that crew totals aggregate correctly in CostTracker."""
        tracker = CostTracker()
        
        crew = CostAwareCrew(
            tasks=sample_tasks,
            agents=sample_agents,
            cost_tracker=tracker,
        )
        
        # Simulate multiple LLM calls during execution
        crew.llm_wrapper.record_completion(prompt_tokens=100, completion_tokens=50)
        crew.llm_wrapper.record_completion(prompt_tokens=200, completion_tokens=100)
        crew.llm_wrapper.record_completion(prompt_tokens=150, completion_tokens=75)
        
        # Check totals
        total_cost = crew.llm_wrapper._total_cost
        total_tokens = crew.llm_wrapper._total_tokens.total_tokens
        
        assert total_tokens == 675  # 450 prompt + 225 completion
        assert len(tracker.entries) == 3
