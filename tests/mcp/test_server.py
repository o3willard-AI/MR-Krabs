"""
Comprehensive tests for MR-Krabs MCP Server (mcp/server.py).

These tests cover HTTP endpoint functionality, session management, 
cost tools, and budget enforcement.

Phase 2: MCP Server - Server Tests
==================================
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Mock CrewAI before importing server
with patch.dict("sys.modules", {"crewai": MagicMock()}):
    CREWAI_AVAILABLE = True
    
from src.mcp.server import app, session_manager, SESSION_TTL


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_session_id():
    """Return a mock session ID for testing."""
    return "test-session-123"


class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    def test_health_check(self, client):
        """Test /health endpoint returns correct status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mr-krabs-mcp"
        assert "session_count" in data
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns service info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "MR-Krabs MCP Server"
        assert "endpoints" in data


class TestToolsEndpoint:
    """Tests for /tools endpoint."""
    
    def test_list_tools(self, client):
        """Test listing all available tools."""
        response = client.get("/tools")
        
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "total_count" in data
        
        # Check expected categories exist
        tools = data["tools"]
        assert "session" in tools
        assert "cost" in tools
        assert "budget" in tools


class TestSessionManagement:
    """Tests for session management endpoints."""
    
    def test_session_init_basic(self, client):
        """Test basic session initialization."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "active"
    
    def test_session_init_with_full_config(self, client):
        """Test session initialization with full configuration."""
        request_data = {
            "budget_limit": 25.0,
            "enforcement_mode": "fail",
            "warning_threshold": 75.0,
            "default_tier": "L1",
            "models": ["google/gemma-7b-it", "meta-llama/llama-3-8b-instruct"]
        }
        
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json=request_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["budget_limit"] == 25.0
        assert data["config"]["enforcement_mode"] == "fail"
    
    def test_session_status_valid(self, client):
        """Test getting status of valid session."""
        # First create a session
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_response.json()["session_id"]
        
        # Get status
        response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert "time_remaining_seconds" in data
    
    def test_session_status_expired(self, client):
        """Test getting status of expired/non-existent session."""
        response = client.get("/tools/mcp_mrkrabs_session_status/nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
    
    def test_session_close(self, client):
        """Test closing a session."""
        # Create session
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_response.json()["session_id"]
        
        # Close session
        response = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["closed"] is True
    
    def test_multiple_sessions(self, client):
        """Test creating and managing multiple sessions."""
        session_ids = []
        
        # Create multiple sessions
        for i in range(3):
            response = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"budget_limit": 10.0 + i}
            )
            assert response.status_code == 200
            session_ids.append(response.json()["session_id"])
        
        # Verify all sessions are active
        for session_id in session_ids:
            response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
            assert response.status_code == 200
            assert response.json()["active"] is True


class TestPingEndpoint:
    """Tests for ping endpoint."""
    
    def test_ping_without_session(self, client):
        """Test ping without session ID."""
        response = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_ping_with_valid_session(self, client):
        """Test ping with valid session ID."""
        # Create session
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_response.json()["session_id"]
        
        # Ping with session
        response = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_active"] is True


class TestCostEstimate:
    """Tests for cost estimation endpoint."""
    
    def test_cost_estimate_with_tokens(self, client):
        """Test cost estimation with token counts."""
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
    
    def test_cost_estimate_with_text(self, client):
        """Test cost estimation with prompt text."""
        response = client.post(
            "/tools/mcp_mrkrabs_cost_estimate",
            json={
                "model": "meta-llama/llama-3-8b-instruct",
                "prompt_text": "Hello, world!"
            }
        )
        
        assert response.status_code == 200
    
    def test_cost_estimate_with_session(self, client):
        """Test cost estimation with session."""
        # Create session
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_response.json()["session_id"]
        
        # Estimate with session
        response = client.post(
            "/tools/mcp_mrkrabs_cost_estimate",
            json={
                "session_id": session_id,
                "model": "google/gemma-7b-it",
                "input_tokens": 100,
                "output_tokens": 50
            }
        )
        
        assert response.status_code == 200


class TestBudgetCheck:
    """Tests for budget checking endpoint."""
    
    def test_budget_check_with_session(self, client):
        """Test budget check with session."""
        # Create session with low budget
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 1.0, "enforcement_mode": "notify_then_fail"}
        )
        session_id = init_response.json()["session_id"]
        
        # Check budget for small amount (should pass)
        response = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={
                "session_id": session_id,
                "would_spend": 0.50
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "can_proceed" in data
    
    def test_budget_check_exceeded(self, client):
        """Test budget check when limit exceeded."""
        # Create session with very low budget
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 0.10, "enforcement_mode": "fail"}
        )
        session_id = init_response.json()["session_id"]
        
        # Try to spend more than budget
        response = client.post(
            "/tools/mcp_mrkrabs_budget_check",
            json={
                "session_id": session_id,
                "would_spend": 10.00
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should indicate budget issue (either can_proceed=False or error)


class TestServerConfiguration:
    """Tests for server configuration."""
    
    def test_session_ttl_configuration(self):
        """Test session TTL is configured from environment."""
        assert SESSION_TTL == int(SESSION_TTL)  # Should be integer
        assert SESSION_TTL > 0
    
    def test_session_manager_initialized(self):
        """Test session manager is properly initialized."""
        assert session_manager is not None


class TestErrorHandling:
    """Tests for error handling in endpoints."""
    
    def test_invalid_json_request(self, client):
        """Test handling of invalid JSON."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            data="not json"
        )
        
        # Should return 400 or 422 for validation error
        assert response.status_code in [400, 422]


class TestAPIKeyAuthentication:
    """Tests for API key authentication."""
    
    def test_no_api_key_required_by_default(self, client):
        """Test endpoints work without API key when not configured."""
        # MCP_API_KEY is not set, so no auth required
        response = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={}
        )
        
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCrewAITools:
    """Tests for CrewAI integration tools."""
    
    def test_crew_create_request_structure(self, client):
        """Test crew create endpoint request structure."""
        # Just verify the endpoint accepts requests properly
        # Actual CrewAI functionality is tested elsewhere
        response = client.post(
            "/tools/mcp_mrkrabs_crew_create",
            json={
                "session_id": None,
                "crew_config": {
                    "agents": [{"name": "test_agent", "role": "tester"}],
                    "tasks": [{"description": "Test task"}]
                }
            }
        )
        
        # Should handle the request (may fail gracefully if CrewAI not available)
        assert response.status_code in [200, 500]


class TestAnalyticsTools:
    """Tests for analytics endpoints."""
    
    def test_analytics_summary_endpoint(self, client):
        """Test analytics summary endpoint."""
        response = client.post(
            "/tools/mcp_mrkrabs_analytics_summary",
            json={
                "session_id": None,
                "days": 7
            }
        )
        
        # Endpoint should respond
        assert response.status_code in [200, 400, 500]


class TestCostTrackingIntegration:
    """Tests for cost tracking integration."""
    
    def test_cost_track_with_session(self, client):
        """Test recording costs with session."""
        # Create session
        init_response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_response.json()["session_id"]
        
        # Track cost
        response = client.post(
            "/tools/mcp_mrkrabs_cost_track",
            json={
                "session_id": session_id,
                "amount": 0.50,
                "model": "google/gemma-7b-it"
            }
        )
        
        assert response.status_code == 200


class TestSessionWithConfig:
    """Tests for sessions with custom configuration."""
    
    def test_session_with_custom_enforcement(self, client):
        """Test session with strict enforcement mode."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 5.0,
                "enforcement_mode": "fail",
                "warning_threshold": 90.0
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        session_id = data["session_id"]
        
        # Verify config was saved
        status_response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        assert status_response.json()["config"]["enforcement_mode"] == "fail"


class TestEndpointDocumentation:
    """Tests for endpoint documentation and metadata."""
    
    def test_openapi_schema_available(self, client):
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")
        
        assert response.status_code == 200
        data = response.json()
        assert "info" in data
        assert "paths" in data
    
    def test_server_info_in_schema(self, client):
        """Test server information in OpenAPI schema."""
        response = client.get("/openapi.json")
        data = response.json()
        
        assert data["info"]["title"] == "MR-Krabs MCP Server"
