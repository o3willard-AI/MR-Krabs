"""
MR-Krabs Integration Test Framework

Provides integration tests for the MCP server with realistic scenarios.
Tests actual HTTP endpoints without requiring authentication (auth disabled by default).

Test Categories:
- Endpoint availability
- Request/response validation
- Workflow scenarios
- Error handling
"""

import pytest
import requests
import time
import os
import json
from datetime import datetime
from typing import Optional


# Server configuration for integration tests
TEST_SERVER_URL = os.getenv("MCP_TEST_URL", "http://localhost:8000")
SERVER_TIMEOUT = 30  # seconds

# Session management helper
class TestSession:
    """Helper class for managing test sessions."""
    
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self.session_id: Optional[str] = None
    
    def create_session(self) -> dict:
        """Create a new test session."""
        response = requests.post(
            f"{self.server_url}/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 50.0,
                "enforcement_mode": "notify_only",
                "warning_threshold": 80.0
            },
            timeout=10
        )
        
        assert response.status_code == 200, f"Failed to create session: {response.text}"
        self.session_id = response.json()["session_id"]
        return response.json()
    
    def close_session(self) -> dict:
        """Close the current test session."""
        if not self.session_id:
            return {"closed": False, "message": "No active session"}
        
        response = requests.delete(
            f"{self.server_url}/tools/mcp_mrkrabs_session_close/{self.session_id}",
            timeout=10
        )
        
        result = response.json()
        self.session_id = None
        return result


class TestServerHealth:
    """Test server health and availability."""
    
    def test_server_is_running(self):
        """Verify the server is responding."""
        response = requests.get(f"{TEST_SERVER_URL}/health", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
    
    def test_root_endpoint(self):
        """Test root endpoint returns service info."""
        response = requests.get(f"{TEST_SERVER_URL}/", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "MR-Krabs MCP Server"
        assert "endpoints" in data
    
    def test_tools_list_endpoint(self):
        """Test tools list returns all available tools."""
        response = requests.get(f"{TEST_SERVER_URL}/tools", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check all categories are present
        assert "tools" in data
        assert "session" in data["tools"]
        assert "cost" in data["tools"]
        assert "crew" in data["tools"]
        assert "agent" in data["tools"]
        assert "analytics" in data["tools"]


class TestSessionManagement:
    """Test session lifecycle operations."""
    
    def test_create_session(self):
        """Test creating a new session."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 100.0,
                "enforcement_mode": "notify_then_fail"
            },
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "session_id" in data
        assert data["status"] == "active"
        assert "config" in data
        
        # Clean up
        requests.delete(f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_close/{data['session_id']}")
    
    def test_session_status(self):
        """Test checking session status."""
        # Create session
        create_response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 25.0},
            timeout=10
        )
        session_id = create_response.json()["session_id"]
        
        # Check status
        status_response = requests.get(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_status/{session_id}",
            timeout=10
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["active"] is True
        
        # Clean up
        requests.delete(f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_close/{session_id}")
    
    def test_close_session(self):
        """Test closing a session."""
        # Create session
        create_response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 15.0},
            timeout=10
        )
        session_id = create_response.json()["session_id"]
        
        # Close session
        close_response = requests.delete(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_close/{session_id}",
            timeout=10
        )
        
        assert close_response.status_code == 200
        data = close_response.json()
        assert data["closed"] is True
        
        # Verify session is gone
        status_response = requests.get(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_status/{session_id}",
            timeout=10
        )
        
        status_data = status_response.json()
        assert status_data["active"] is False


class TestAnalyticsTools:
    """Test analytics tool endpoints."""
    
    def test_analytics_summary(self):
        """Test analytics summary endpoint."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_analytics_summary",
            json={"period_days": 7},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "total_spent" in data["data"]
        assert "task_count" in data["data"]
    
    def test_tier_breakdown(self):
        """Test tier breakdown endpoint."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_tier_breakdown",
            json={"period_days": 7},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "tiers" in data["data"]
        assert "L0" in data["data"]["tiers"]
    
    def test_cost_trends(self):
        """Test cost trends endpoint with ASCII chart."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_cost_trends",
            json={"period_days": 7},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "trend_direction" in data["data"]
        assert "ascii_chart" in data["data"]
        assert len(data["data"]["ascii_chart"]) > 0
    
    def test_efficiency_report(self):
        """Test efficiency report endpoint."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_efficiency_report",
            json={"period_days": 7},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "overall_efficiency_score" in data["data"]
        assert "optimization_suggestions" in data["data"]


class TestCostManagementTools:
    """Test cost management tool endpoints."""
    
    def test_cost_estimate(self):
        """Test cost estimation endpoint."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_cost_estimate",
            json={
                "model": "google/gemma-7b-it",
                "input_tokens": 100,
                "output_tokens": 50
            },
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "estimated_cost" in data
        assert isinstance(data["estimated_cost"], (int, float))
    
    def test_budget_check(self):
        """Test budget check endpoint."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_budget_check",
            json={
                "config": {"budget_limit": 10.0, "enforcement_mode": "notify_only"},
                "would_spend": 2.50
            },
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "can_proceed" in data
        assert isinstance(data["can_proceed"], bool)


class TestCrewAIVerification:
    """Test CrewAI tool validation (without execution)."""
    
    def test_crew_create_validation(self):
        """Test crew creation validates configuration."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_crew_create",
            json={
                "crew_config": {
                    "name": "test-crew",
                    "agents": [
                        {
                            "name": "researcher",
                            "role": "Researcher",
                            "goal": "Research topics",
                            "backstory": "Expert researcher"
                        }
                    ],
                    "tasks": [
                        {
                            "description": "Test task",
                            "agent_name": "researcher"
                        }
                    ]
                }
            },
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should validate configuration even if CrewAI not fully integrated
        assert "success" in data or "message" in data
    
    def test_crew_execute_validation(self):
        """Test crew execution validates input."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_crew_execute",
            json={
                "crew_config": {
                    "name": "test-crew",
                    "agents": [
                        {
                            "name": "writer",
                            "role": "Writer",
                            "goal": "Write content",
                            "backstory": "Skilled writer"
                        }
                    ],
                    "tasks": [
                        {
                            "description": "Write something",
                            "agent_name": "writer"
                        }
                    ]
                }
            },
            timeout=10
        )
        
        # Should return a response (success or graceful degradation)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data or "message" in data or "error" in data


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_model_id(self):
        """Test handling of invalid model ID."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_cost_estimate",
            json={
                "model": "invalid/model/that/does/not/exist-xyz123",
                "input_tokens": 100,
                "output_tokens": 50
            },
            timeout=10
        )
        
        # Should handle gracefully (either error or fallback)
        assert response.status_code in [200, 400, 500]
    
    def test_missing_required_field(self):
        """Test handling of missing required fields."""
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_analytics_summary",
            json={},  # Missing all fields but has defaults
            timeout=10
        )
        
        # Should work with defaults or return appropriate error
        assert response.status_code in [200, 422]
    
    def test_invalid_session_id(self):
        """Test handling of invalid session ID."""
        response = requests.get(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_status/invalid-session-id-12345",
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False


class TestPerformance:
    """Basic performance sanity checks."""
    
    def test_response_time_health(self):
        """Test health endpoint responds quickly."""
        start = time.time()
        response = requests.get(f"{TEST_SERVER_URL}/health", timeout=5)
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Health check should be fast (< 1 second)
        assert elapsed < 1.0
    
    def test_response_time_analytics(self):
        """Test analytics endpoint responds reasonably."""
        start = time.time()
        response = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_analytics_summary",
            json={"period_days": 7},
            timeout=10
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Analytics should complete within 5 seconds (with mock data)
        assert elapsed < 5.0


class TestIntegrationWorkflows:
    """Test complete workflow scenarios."""
    
    def test_complete_analytics_workflow(self):
        """Test complete analytics review workflow."""
        # Step 1: Get summary
        summary = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_analytics_summary",
            json={"period_days": 7},
            timeout=10
        ).json()
        
        assert summary["success"] is True
        
        # Step 2: Get tier breakdown
        breakdown = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_tier_breakdown",
            json={"period_days": 7},
            timeout=10
        ).json()
        
        assert breakdown["success"] is True
        
        # Step 3: Get trends
        trends = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_cost_trends",
            json={"period_days": 7},
            timeout=10
        ).json()
        
        assert trends["success"] is True
        
        # Step 4: Get efficiency report
        efficiency = requests.post(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_efficiency_report",
            json={"period_days": 7},
            timeout=10
        ).json()
        
        assert efficiency["success"] is True
        
        # Verify all data is consistent
        assert summary["data"]["period"] == "7 days"
        assert breakdown["data"]["period"] == "7 days"
        assert trends["data"]["period"] == "7 days"
    
    def test_session_workflow(self):
        """Test complete session lifecycle."""
        test_session = TestSession(TEST_SERVER_URL)
        
        # Create session
        create_result = test_session.create_session()
        assert create_result["status"] == "active"
        assert "session_id" in create_result
        
        # Use session (check status)
        status_response = requests.get(
            f"{TEST_SERVER_URL}/tools/mcp_mrkrabs_session_status/{test_session.session_id}",
            timeout=10
        )
        assert status_response.status_code == 200
        assert status_response.json()["active"] is True
        
        # Close session
        close_result = test_session.close_session()
        assert close_result["closed"] is True


@pytest.fixture(scope="module")
def server_url():
    """Provide server URL for tests."""
    return TEST_SERVER_URL


if __name__ == "__main__":
    print(f"Running integration tests against: {TEST_SERVER_URL}")
    print("=" * 60)
    
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short", "--timeout=30"])
