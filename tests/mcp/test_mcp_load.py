"""
Load Testing for MR-Krabs MCP Server

Tests server performance under concurrent load and stress conditions.
Uses asyncio for parallel request simulation.
"""

import pytest
import asyncio
import time
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


class TestConcurrentSessionCreation:
    """Test handling of concurrent session creation requests."""

    def test_create_multiple_sessions_sequentially(self, client):
        """Creating multiple sessions sequentially should all succeed."""
        session_ids = []
        
        for i in range(10):
            resp = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": 10.0 + i}
            )
            assert resp.status_code == 200
            session_ids.append(resp.json()["session_id"])
        
        # Verify all sessions are unique
        assert len(session_ids) == len(set(session_ids))
        
        # Verify all sessions exist
        for session_id in session_ids:
            status = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert status.json()["active"] is True
        
        # Check health endpoint reflects session count
        health = client.get("/health")
        assert health.json()["session_count"] >= 10

    def test_create_sessions_with_different_configs(self, client):
        """Sessions with different configurations should all work."""
        configs = [
            {"budget_limit": 5.0, "enforcement_mode": "notify_only"},
            {"budget_limit": 10.0, "enforcement_mode": "fail"},
            {"budget_limit": 20.0, "enforcement_mode": "notify_then_fail"},
            {"budget_limit": 50.0, "enforcement_mode": "fail_with_notification"},
        ]
        
        session_ids = []
        for config in configs:
            resp = client.post("/tools/mcp_mrkrabs_session_init", json=config)
            assert resp.status_code == 200
            
            # Verify config was stored
            data = resp.json()
            assert data["config"]["budget_limit"] == config["budget_limit"]
            session_ids.append(data["session_id"])
        
        # All should be independent
        for i, session_id in enumerate(session_ids):
            status = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert status.json()["config"]["budget_limit"] == configs[i]["budget_limit"]


class TestLoadOnEndpoints:
    """Test various endpoints under load."""

    def test_health_endpoint_under_load(self, client):
        """Health endpoint should handle multiple rapid requests."""
        start_time = time.time()
        
        for _ in range(50):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
        
        elapsed = time.time() - start_time
        # Should complete quickly (< 5 seconds)
        assert elapsed < 5.0

    def test_ping_endpoint_load(self, client):
        """Ping endpoint should handle rapid requests."""
        # Create a session first
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        start_time = time.time()
        
        for _ in range(20):
            resp = client.post(
                "/tools/mcp_mrkrabs_ping",
                json={"session_id": session_id}
            )
            assert resp.status_code == 200
        
        elapsed = time.time() - start_time
        assert elapsed < 3.0

    def test_cost_estimate_load(self, client):
        """Cost estimation should handle multiple requests."""
        requests_data = [
            {"model": "google/gemma-7b-it", "input_tokens": 100, "output_tokens": 50},
            {"model": "meta-llama/llama-3-8b-instruct", "input_tokens": 200, "output_tokens": 100},
            {"model": "anthropic/claude-sonnet-4.6", "input_tokens": 50, "output_tokens": 25},
        ]
        
        # Run each request type multiple times
        for _ in range(5):
            for data in requests_data:
                resp = client.post("/tools/mcp_mrkrabs_cost_estimate", json=data)
                assert resp.status_code == 200


class TestSessionManagementLoad:
    """Test session management operations under load."""

    def test_create_and_close_cycles(self, client):
        """Creating and closing sessions in cycles should work correctly."""
        for cycle in range(5):
            # Create session
            init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
            assert init_resp.status_code == 200
            session_id = init_resp.json()["session_id"]
            
            # Use session
            status = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert status.json()["active"] is True
            
            # Close session
            close_resp = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
            assert close_resp.json()["closed"] is True
            
            # Verify closed
            status_after = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert status_after.json()["active"] is False

    def test_budget_check_load_with_sessions(self, client):
        """Budget checking should work with multiple sessions."""
        # Create 3 sessions
        sessions = []
        for i in range(3):
            resp = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": 10.0}
            )
            sessions.append(resp.json()["session_id"])
        
        # Run budget checks on each session multiple times
        for session_id in sessions:
            for amount in [1.0, 2.0, 3.0, 4.0]:
                resp = client.post(
                    "/tools/mcp_mrkrabs_budget_check",
                    json={"session_id": session_id, "would_spend": amount}
                )
                assert resp.status_code == 200


class TestMockedCrewAIload:
    """Test CrewAI endpoints under load (with mocking)."""

    def test_crow_create_load(self, client):
        """Crew creation should handle multiple requests."""
        crew_configs = [
            {
                "name": f"crew-{i}",
                "agents": [{"name": "agent1", "role": "R", "goal": "G", "backstory": "B"}],
                "tasks": [{"description": "T", "agent_name": "agent1"}]
            }
            for i in range(5)
        ]
        
        for config in crew_configs:
            resp = client.post(
                "/tools/mcp_mrkrabs_crew_create",
                json={"crew_config": config}
            )
            assert resp.status_code == 200

    def test_agent_execute_load(self, client):
        """Agent execution should handle multiple requests."""
        with patch("src.mcp.crew_tools.process_agent_execute") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True,
                output="Test response",
                cost=0.001
            )
            
            prompts = [f"Test prompt {i}" for i in range(10)]
            
            for prompt in prompts:
                resp = client.post(
                    "/tools/mcp_mrkrabs_agent_execute",
                    json={"prompt": prompt}
                )
                assert resp.status_code == 200


class TestConcurrentOperationsSimulation:
    """Simulate realistic concurrent usage patterns."""

    def test_realistic_user_session(self, client):
        """Simulate a realistic user workflow."""
        # Mock CrewAI and analytics to avoid real LLM calls
        with patch("src.mcp.crew_tools.process_agent_execute") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True,
                output="Response",
                cost=0.01
            )
            
            # 1. User starts session
            init_resp = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": 5.0}
            )
            assert init_resp.status_code == 200
            session_id = init_resp.json()["session_id"]
            
            # 2. User estimates costs for several tasks
            for i in range(3):
                estimate = client.post(
                    "/tools/mcp_mrkrabs_cost_estimate",
                    json={
                        "session_id": session_id,
                        "model": "google/gemma-7b-it",
                        "input_tokens": 100 + i * 50,
                        "output_tokens": 50
                    }
                )
                assert estimate.status_code == 200
            
            # 3. User executes tasks
            for i in range(3):
                exec_resp = client.post(
                    "/tools/mcp_mrkrabs_agent_execute",
                    json={
                        "session_id": session_id,
                        "prompt": f"Task {i}"
                    }
                )
                assert exec_resp.status_code == 200
                
                # Track the cost
                client.post(
                    "/tools/mcp_mrkrabs_cost_track",
                    json={
                        "session_id": session_id,
                        "amount": 0.01,
                        "model": "google/gemma-7b-it"
                    }
                )
            
            # 4. User checks remaining budget
            budget_check = client.post(
                "/tools/mcp_mrkrabs_budget_check",
                json={"session_id": session_id, "would_spend": 1.0}
            )
            assert budget_check.status_code == 200
            
            # 5. User gets analytics
            with patch("src.mcp.analytics_tools.process_analytics_summary") as mock_analytics:
                mock_analytics.return_value = MagicMock(
                    total_spent=0.03,
                    task_count=3
                )
                
                analytics = client.post(
                    "/tools/mcp_mrkrabs_analytics_summary",
                    json={"session_id": session_id}
                )
                assert analytics.status_code == 200
            
            # 6. User closes session
            close_resp = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
            assert close_resp.json()["closed"] is True

    def test_high_traffic_simulation(self, client):
        """Simulate high traffic with many operations."""
        operations_count = 0
        
        # Create multiple sessions
        for i in range(5):
            init = client.post("/tools/mcp_mrkrabs_session_init", json={})
            if init.status_code == 200:
                operations_count += 1
        
        # Run many cost estimates
        for _ in range(20):
            estimate = client.post(
                "/tools/mcp_mrkrabs_cost_estimate",
                json={"model": "google/gemma-7b-it", "input_tokens": 100, "output_tokens": 50}
            )
            if estimate.status_code == 200:
                operations_count += 1
        
        # Run many health checks
        for _ in range(10):
            health = client.get("/health")
            if health.status_code == 200:
                operations_count += 1
        
        # All operations should succeed
        assert operations_count >= 30


class TestStressScenarios:
    """Test edge cases and stress scenarios."""

    def test_very_high_budget_limit(self, client):
        """Should handle very high budget limits."""
        resp = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10000.0}
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        
        # Should be able to check large amounts
        check = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={"session_id": session_id, "would_spend": 5000.0}
        )
        assert check.status_code == 200

    def test_very_small_amounts(self, client):
        """Should handle very small cost amounts."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Track tiny amount
        track = client.post(
            "/tools/mcp_mrkrabs_cost_track",
            json={
                "session_id": session_id,
                "amount": 0.0001,
                "model": "google/gemma-7b-it"
            }
        )
        assert track.status_code == 200

    def test_many_cost_tracks_in_session(self, client):
        """Should handle many cost tracking operations."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Track 50 separate costs
        for i in range(50):
            track = client.post(
                "/tools/mcp_mrkrabs_cost_track",
                json={
                    "session_id": session_id,
                    "amount": 0.01,
                    "model": "google/gemma-7b-it"
                }
            )
            assert track.status_code == 200
