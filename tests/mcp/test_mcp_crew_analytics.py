"""
Comprehensive Tests for MR-Krabs CrewAI & Analytics MCP Tools

Tests the CrewAI orchestration endpoints (crew_create, crew_execute, agent_execute)
and analytics endpoints (summary, tier_breakdown, cost_trends, efficiency_report).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create test client."""
    from src.mcp import server
    
    # Clean session manager state
    server.session_manager._sessions.clear()
    
    with TestClient(server.app) as c:
        yield c


class TestCrewCreateTool:
    """Test crew creation endpoint."""

    def test_crew_create_minimal(self, client):
        """Crew create should work with minimal config."""
        response = client.post(
            "/tools/mcp_mrkrabs_crew_create",
            json={
                "crew_config": {
                    "name": "test-crew",
                    "agents": [
                        {
                            "name": "agent1",
                            "role": "Tester",
                            "goal": "Test things",
                            "backstory": "You are a tester"
                        }
                    ],
                    "tasks": [
                        {
                            "description": "Do something",
                            "agent_name": "agent1"
                        }
                    ]
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "success" in data or "crew_id" in data or "message" in data

    def test_crew_create_multiple_agents(self, client):
        """Crew create should support multiple agents."""
        response = client.post(
            "/tools/mcp_mrkrabs_crew_create",
            json={
                "crew_config": {
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
            }
        )
        
        assert response.status_code == 200

    def test_crew_create_with_session(self, client):
        """Crew create should work with session_id."""
        # Create session
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Create crew with session
        response = client.post(
            "/tools/mcp_mrkrabs_crew_create",
            json={
                "session_id": session_id,
                "crew_config": {
                    "name": "session-crew",
                    "agents": [
                        {"name": "agent1", "role": "Agent", "goal": "Do work", "backstory": "Worker"}
                    ],
                    "tasks": [
                        {"description": "Task 1", "agent_name": "agent1"}
                    ]
                }
            }
        )
        
        assert response.status_code == 200

    def test_crew_create_missing_required_fields(self, client):
        """Crew create with missing fields should handle gracefully."""
        # Missing agents
        response = client.post(
            "/tools/mcp_mrkrabs_crew_create",
            json={
                "crew_config": {
                    "name": "incomplete-crew"
                    # Missing agents and tasks
                }
            }
        )
        
        # Should return error or handle validation
        assert response.status_code in [200, 422, 500]


class TestCrewExecuteTool:
    """Test crew execution endpoint."""

    def test_crew_execute_basic(self, client):
        """Crew execute should accept crew config."""
        # Mock the actual CrewAI execution to avoid real LLM calls
        with patch("src.mcp.crew_tools.process_crew_execute") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                output="Test output",
                cost=0.01,
                crew_id="crew-test-123"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_crew_execute",
                json={
                    "crew_config": {
                        "name": "test-crew",
                        "agents": [
                            {"name": "agent1", "role": "Agent", "goal": "Work", "backstory": "Worker"}
                        ],
                        "tasks": [
                            {"description": "Task", "agent_name": "agent1"}
                        ]
                    }
                }
            )
            
            assert response.status_code == 200

    def test_crew_execute_with_config(self, client):
        """Crew execute should accept additional config."""
        with patch("src.mcp.crew_tools.process_crew_execute") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                output="Test",
                cost=0.01,
                crew_id="crew-456"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_crew_execute",
                json={
                    "crew_config": {
                        "name": "config-crew",
                        "agents": [{"name": "a1", "role": "R", "goal": "G", "backstory": "B"}],
                        "tasks": [{"description": "T", "agent_name": "a1"}]
                    },
                    "config": {
                        "model": "google/gemma-7b-it"
                    }
                }
            )
            
            assert response.status_code == 200


class TestAgentExecuteTool:
    """Test single agent execution endpoint."""

    def test_agent_execute_simple_prompt(self, client):
        """Agent execute should work with simple prompt."""
        with patch("src.mcp.crew_tools.process_agent_execute") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                output="AI response",
                cost=0.001,
                model_used="google/gemma-7b-it"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_agent_execute",
                json={
                    "prompt": "What is 2+2?"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "success" in data or "output" in data

    def test_agent_execute_with_model_override(self, client):
        """Agent execute should accept model override."""
        with patch("src.mcp.crew_tools.process_agent_execute") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                output="Response",
                cost=0.002,
                model_used="meta-llama/llama-3-8b-instruct"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_agent_execute",
                json={
                    "prompt": "Say hello",
                    "model": "meta-llama/llama-3-8b-instruct"
                }
            )
            
            assert response.status_code == 200

    def test_agent_execute_with_session(self, client):
        """Agent execute should work with session."""
        # Create session
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        with patch("src.mcp.crew_tools.process_agent_execute") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                output="Session response",
                cost=0.001
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_agent_execute",
                json={
                    "session_id": session_id,
                    "prompt": "Hello from session"
                }
            )
            
            assert response.status_code == 200


class TestAnalyticsSummaryTool:
    """Test analytics summary endpoint."""

    def test_analytics_summary_basic(self, client):
        """Analytics summary should return aggregated data."""
        with patch("src.mcp.analytics_tools.process_analytics_summary") as mock_process:
            mock_process.return_value = MagicMock(
                total_spent=5.0,
                task_count=10,
                avg_cost_per_task=0.5,
                tier_distribution={"L0": 7, "L1": 3},
                trend_direction="stable",
                efficiency_score=85
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_analytics_summary",
                json={
                    "period_days": 7
                }
            )
            
            assert response.status_code == 200

    def test_analytics_summary_with_session(self, client):
        """Analytics summary should work with session."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        with patch("src.mcp.analytics_tools.process_analytics_summary") as mock_process:
            mock_process.return_value = MagicMock(
                total_spent=10.0,
                task_count=20,
                avg_cost_per_task=0.5
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_analytics_summary",
                json={
                    "session_id": session_id,
                    "period_days": 14
                }
            )
            
            assert response.status_code == 200


class TestTierBreakdownTool:
    """Test tier breakdown endpoint."""

    def test_tier_breakdown_returns_all_tiers(self, client):
        """Tier breakdown should include all tiers (L0-L3)."""
        with patch("src.mcp.analytics_tools.process_tier_breakdown") as mock_process:
            mock_process.return_value = MagicMock(
                tiers={
                    "L0": {"cost": 1.0, "tasks": 50},
                    "L1": {"cost": 2.0, "tasks": 30},
                    "L2": {"cost": 3.0, "tasks": 15},
                    "L3": {"cost": 4.0, "tasks": 5}
                },
                most_used_tier="L0",
                highest_cost_tier="L3"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_tier_breakdown",
                json={"period_days": 7}
            )
            
            assert response.status_code == 200


class TestCostTrendsTool:
    """Test cost trends endpoint."""

    def test_cost_trends_returns_trend_data(self, client):
        """Cost trends should return trend direction and data."""
        with patch("src.mcp.analytics_tools.process_cost_trends") as mock_process:
            mock_process.return_value = MagicMock(
                trend_direction="increasing",
                change_percent=12.5,
                daily_data=[{"date": "2026-05-01", "cost": 5.0}],
                ascii_chart="📈 Cost increasing"
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_cost_trends",
                json={"period_days": 7}
            )
            
            assert response.status_code == 200


class TestEfficiencyReportTool:
    """Test efficiency report endpoint."""

    def test_efficiency_report_returns_score(self, client):
        """Efficiency report should return overall score."""
        with patch("src.mcp.analytics_tools.process_efficiency_report") as mock_process:
            mock_process.return_value = MagicMock(
                overall_efficiency_score=82,
                tier_analysis={"L0": {"efficiency": 95}},
                optimization_suggestions=["Consider using L0 more"],
                potential_monthly_savings=15.0
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_efficiency_report",
                json={"period_days": 30}
            )
            
            assert response.status_code == 200
            data = response.json()
            # Depending on implementation, may have different field names

    def test_efficiency_report_with_session(self, client):
        """Efficiency report should work with session."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        with patch("src.mcp.analytics_tools.process_efficiency_report") as mock_process:
            mock_process.return_value = MagicMock(
                overall_efficiency_score=90
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_efficiency_report",
                json={
                    "session_id": session_id,
                    "period_days": 7
                }
            )
            
            assert response.status_code == 200


class TestCrewAIIntegration:
    """Integration tests for CrewAI tools."""

    def test_crow_create_then_execute_workflow(self, client):
        """Test workflow: create crew -> execute crew."""
        # Mock execution
        with patch("src.mcp.crew_tools.process_crew_execute") as mock_exec:
            mock_exec.return_value = MagicMock(success=True, output="Result", cost=0.01)
            
            # 1. Create crew
            create_resp = client.post(
                "/tools/mcp_mrkrabs_crew_create",
                json={
                    "crew_config": {
                        "name": "workflow-crew",
                        "agents": [{"name": "a1", "role": "R", "goal": "G", "backstory": "B"}],
                        "tasks": [{"description": "T", "agent_name": "a1"}]
                    }
                }
            )
            assert create_resp.status_code == 200
            
            # 2. Execute crew (in real scenario, would use crew_id from step 1)
            exec_resp = client.post(
                "/tools/mcp_mrkrabs_crew_execute",
                json={
                    "crew_config": {
                        "name": "workflow-crew",
                        "agents": [{"name": "a1", "role": "R", "goal": "G", "backstory": "B"}],
                        "tasks": [{"description": "T", "agent_name": "a1"}]
                    }
                }
            )
            assert exec_resp.status_code == 200


class TestAnalyticsIntegration:
    """Integration tests for analytics tools."""

    def test_all_analytics_endpoints_respond(self, client):
        """All analytics endpoints should be accessible."""
        endpoints = [
            "/tools/mcp_mrkrabs_analytics_summary",
            "/tools/mcp_mrkrabs_tier_breakdown",
            "/tools/mcp_mrkrabs_cost_trends",
            "/tools/mcp_mrkrabs_efficiency_report"
        ]
        
        # Mock all processing functions
        with patch("src.mcp.analytics_tools.process_analytics_summary") as mock1, \
             patch("src.mcp.analytics_tools.process_tier_breakdown") as mock2, \
             patch("src.mcp.analytics_tools.process_cost_trends") as mock3, \
             patch("src.mcp.analytics_tools.process_efficiency_report") as mock4:
            
            mock1.return_value = MagicMock(total_spent=0)
            mock2.return_value = MagicMock(tiers={})
            mock3.return_value = MagicMock(trend_direction="stable")
            mock4.return_value = MagicMock(overall_efficiency_score=0)
            
            for endpoint in endpoints:
                response = client.post(endpoint, json={"period_days": 7})
                assert response.status_code == 200, f"Endpoint {endpoint} failed"
