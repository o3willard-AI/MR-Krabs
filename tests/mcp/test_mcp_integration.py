"""
End-to-End Integration Tests for MR-Krabs MCP Server

Tests complete workflows combining multiple endpoints and simulating real usage patterns.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create test client with clean state."""
    from src.mcp import server
    
    # Clean session manager state
    server.session_manager._sessions.clear()
    
    with TestClient(server.app) as c:
        yield c


class TestCompleteWorkflowIntegration:
    """Test complete user workflows."""

    def test_session_with_cost_estimation_and_tracking(self, client):
        """Complete workflow: create session -> estimate cost -> check budget -> track spending."""
        # 1. Initialize session with budget
        init_resp = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 50.0,
                "enforcement_mode": "notify_then_fail"
            }
        )
        assert init_resp.status_code == 200
        session_id = init_resp.json()["session_id"]
        
        # 2. Check initial budget status
        check_resp = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={"session_id": session_id, "would_spend": 5.0}
        )
        assert check_resp.status_code == 200
        
        # 3. Estimate cost for a task
        estimate_resp = client.post(
            "/tools/mcp_mrkrabs_cost_estimate",
            json={
                "session_id": session_id,
                "model": "google/gemma-7b-it",
                "input_tokens": 500,
                "output_tokens": 200
            }
        )
        assert estimate_resp.status_code == 200
        estimated_cost = estimate_resp.json()["estimated_cost"]
        
        # 4. Track the cost
        track_resp = client.post(
            "/tools/mcp_mrkrabs_cost_track",
            json={
                "session_id": session_id,
                "amount": estimated_cost,
                "model": "google/gemma-7b-it"
            }
        )
        assert track_resp.status_code == 200
        
        # 5. Verify budget check after spending
        final_check = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={"session_id": session_id, "would_spend": 45.0}
        )
        assert final_check.status_code == 200
        
        # 6. Close session
        close_resp = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        assert close_resp.status_code == 200
        assert close_resp.json()["closed"] is True

    def test_crowai_workflow_with_session(self, client):
        """Complete CrewAI workflow within a session."""
        # Mock crew execution to avoid real LLM calls
        with patch("src.mcp.crew_tools.process_crew_execute") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True,
                output="Crew completed successfully",
                cost=0.15,
                crew_id="crew-test-123"
            )
            
            # 1. Create session
            init_resp = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": 10.0}
            )
            assert init_resp.status_code == 200
            session_id = init_resp.json()["session_id"]
            
            # 2. Create crew config
            create_resp = client.post(
                "/tools/mcp_mrkrabs_crew_create",
                json={
                    "session_id": session_id,
                    "crew_config": {
                        "name": "research-crew",
                        "agents": [
                            {"name": "researcher", "role": "Researcher", "goal": "Research", "backstory": "Expert"},
                            {"name": "writer", "role": "Writer", "goal": "Write", "backstory": "Skilled"}
                        ],
                        "tasks": [
                            {"description": "Research AI trends", "agent_name": "researcher"},
                            {"description": "Write article", "agent_name": "writer"}
                        ]
                    }
                }
            )
            assert create_resp.status_code == 200
            
            # 3. Execute crew
            exec_resp = client.post(
                "/tools/mcp_mrkrabs_crew_execute",
                json={
                    "session_id": session_id,
                    "crew_config": {
                        "name": "research-crew",
                        "agents": [
                            {"name": "researcher", "role": "Researcher", "goal": "Research", "backstory": "Expert"},
                            {"name": "writer", "role": "Writer", "goal": "Write", "backstory": "Skilled"}
                        ],
                        "tasks": [
                            {"description": "Research AI trends", "agent_name": "researcher"},
                            {"description": "Write article", "agent_name": "writer"}
                        ]
                    }
                }
            )
            assert exec_resp.status_code == 200
            
            # 4. Get analytics summary
            with patch("src.mcp.analytics_tools.process_analytics_summary") as mock_analytics:
                mock_analytics.return_value = MagicMock(
                    total_spent=0.15,
                    task_count=1,
                    avg_cost_per_task=0.15
                )
                
                analytics_resp = client.post(
                    "/tools/mcp_mrkrabs_analytics_summary",
                    json={"session_id": session_id, "period_days": 1}
                )
                assert analytics_resp.status_code == 200

    def test_multiple_concurrent_sessions(self, client):
        """Multiple sessions should work independently."""
        # Create 3 sessions with different budgets
        sessions = []
        for budget in [10.0, 50.0, 100.0]:
            resp = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": budget}
            )
            assert resp.status_code == 200
            sessions.append((resp.json()["session_id"], budget))
        
        # Verify each session has correct budget
        for session_id, expected_budget in sessions:
            status = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert status.json()["config"]["budget_limit"] == expected_budget
        
        # Track different amounts for each session
        for i, (session_id, budget) in enumerate(sessions):
            amount = budget * 0.1  # Spend 10% of budget
            track_resp = client.post(
                "/tools/mcp_mrkrabs_cost_track",
                json={
                    "session_id": session_id,
                    "amount": amount,
                    "model": "google/gemma-7b-it"
                }
            )
            assert track_resp.status_code == 200
        
        # Close middle session only
        client.delete(f"/tools/mcp_mrkrabs_session_close/{sessions[1][0]}")
        
        # Verify middle is closed, others still active
        for i, (session_id, _) in enumerate(sessions):
            status = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            if i == 1:
                assert status.json()["active"] is False
            else:
                assert status.json()["active"] is True


class TestErrorHandlingIntegration:
    """Test error handling and edge cases."""

    def test_nonexistent_session_handling(self, client):
        """Operations on nonexistent sessions should fail gracefully."""
        fake_session_id = "nonexistent-session-12345"
        
        # Session status should return inactive
        status = client.get(f"/tools/mcp_mrkrabs_session_status/{fake_session_id}")
        assert status.status_code == 200
        assert status.json()["active"] is False
        
        # Budget check should fail with 404
        budget_check = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={"session_id": fake_session_id, "would_spend": 5.0}
        )
        assert budget_check.status_code == 404
        
        # Cost tracking should fail with 404
        cost_track = client.post(
            "/tools/mcp_mrkrabs_cost_track",
            json={"session_id": fake_session_id, "amount": 5.0}
        )
        assert cost_track.status_code == 404
        
        # Closing should return closed=False
        close = client.delete(f"/tools/mcp_mrkrabs_session_close/{fake_session_id}")
        assert close.json()["closed"] is False

    def test_zero_and_negative_amounts(self, client):
        """Cost tracking should handle edge case amounts."""
        # Create session
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Track zero amount (should work or be handled)
        track_zero = client.post(
            "/tools/mcp_mrkrabs_cost_track",
            json={"session_id": session_id, "amount": 0.0}
        )
        assert track_zero.status_code == 200


class TestStatelessOperationIntegration:
    """Test stateless operation modes (without sessions)."""

    def test_stateless_cost_estimate(self, client):
        """Cost estimation should work without session."""
        response = client.post(
            "/tools/mcp_mrkrabs_cost_estimate",
            json={
                "model": "google/gemma-7b-it",
                "input_tokens": 100,
                "output_tokens": 50
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "estimated_cost" in data

    def test_stateless_budget_check(self, client):
        """Budget check should work with inline config."""
        response = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={
                "config": {
                    "budget_limit": 10.0,
                    "enforcement_mode": "notify_only"
                },
                "would_spend": 5.0
            }
        )
        
        assert response.status_code == 200

    def test_stateless_crowai_execution(self, client):
        """CrewAI execution should work without session."""
        with patch("src.mcp.crew_tools.process_crew_execute") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True,
                output="Stateless crew result",
                cost=0.10
            )
            
            response = client.post(
                "/tools/mcp_mrkrabs_crew_execute",
                json={
                    "crew_config": {
                        "name": "stateless-crew",
                        "agents": [{"name": "a1", "role": "R", "goal": "G", "backstory": "B"}],
                        "tasks": [{"description": "T", "agent_name": "a1"}]
                    }
                }
            )
            
            assert response.status_code == 200


class TestHealthAndMonitoringIntegration:
    """Test health check and monitoring endpoints."""

    def test_health_reflects_session_count(self, client):
        """Health endpoint should accurately report session count."""
        # Initial count
        health1 = client.get("/health")
        initial_count = health1.json()["session_count"]
        
        # Create 2 sessions
        client.post("/tools/mcp_mrkrabs_session_init", json={})
        client.post("/tools/mcp_mrkrabs_session_init", json={})
        
        # Count should increase
        health2 = client.get("/health")
        assert health2.json()["session_count"] == initial_count + 2
        
        # Close one session
        sessions = list(client.post("/tools/mcp_mrkrabs_session_init", json={}).json()["session_id"],)
        client.delete(f"/tools/mcp_mrkrabs_session_close/{sessions[0]}")
        
        # Count should reflect the change
        health3 = client.get("/health")
        assert health3.json()["session_count"] >= initial_count

    def test_ping_validates_session_status(self, client):
        """Ping endpoint should correctly validate session status."""
        # Ping without session
        ping1 = client.post("/tools/mcp_mrkrabs_ping", json={})
        assert ping1.json()["status"] == "ok"
        
        # Create session and ping with it
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        ping2 = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id}
        )
        assert ping2.json()["session_active"] is True
        
        # Close session and verify
        client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        
        ping3 = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id}
        )
        assert ping3.json()["session_active"] is False


class TestToolDiscoveryIntegration:
    """Test tool discovery and listing."""

    def test_all_tools_listed(self, client):
        """Tools endpoint should list all expected tools."""
        response = client.get("/tools")
        assert response.status_code == 200
        
        data = response.json()
        tools = data["tools"]
        
        # Verify all categories present
        expected_categories = ["session", "cost", "budget", "crew", "agent", "analytics"]
        for category in expected_categories:
            assert category in tools, f"Missing category: {category}"
            
        # Verify specific tools exist
        session_tools = [t["name"] for t in tools["session"]]
        assert "mcp_mrkrabs_session_init" in session_tools
        assert "mcp_mrkrabs_session_status" in session_tools
        assert "mcp_mrkrabs_session_close" in session_tools
        
        cost_tools = [t["name"] for t in tools["cost"]]
        assert "mcp_mrkrabs_cost_estimate" in cost_tools
        assert "mcp_mrkrabs_cost_track" in cost_tools

    def test_tool_count_matches_actual_endpoints(self, client):
        """Total tool count should match the number of listed tools."""
        response = client.get("/tools")
        data = response.json()
        
        calculated_total = sum(len(v) for v in data["tools"].values())
        assert data["total_count"] == calculated_total
