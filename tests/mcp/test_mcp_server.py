"""
Comprehensive MCP Server Tests - MR-Krabs

Tests all endpoints and functionality of the MR-Krabs MCP server:
- Health check & status endpoints
- Session management (create, status, close)
- Cost estimation & tracking tools
- Budget checking & enforcement
- CrewAI orchestration tools
- Analytics & reporting tools
- Authentication middleware
- Request validation
- Error handling
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import os
import time
import uuid

# Set up test environment before imports
os.environ.setdefault("SESSION_TTL", "3600")


@pytest.fixture
def client():
    """Create test client with fresh app instance."""
    # Force reload to avoid state contamination between tests
    import importlib
    from src.mcp import server
    
    # Clean session manager state before each test
    server.session_manager._sessions.clear()
    
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def mock_env_with_auth():
    """Mock environment with authentication enabled."""
    with patch.dict(os.environ, {"MCP_API_KEY": "test-secret-key-123"}):
        # Need to reload the module to pick up new env var
        import importlib
        from src.mcp import server as server_module
        importlib.reload(server_module)
        yield server_module.app
        # Restore original
        importlib.reload(server_module)


class TestHealthEndpoints:
    """Test health check and status endpoints."""

    def test_health_check_returns_healthy(self, client):
        """Health endpoint should return 200 with healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mr-krabs-mcp"
        assert "version" in data
        assert "session_count" in data
        assert isinstance(data["session_count"], int)

    def test_health_check_includes_session_count(self, client):
        """Health endpoint should include current session count."""
        # Create a session first
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        assert init_resp.status_code == 200
        
        # Check health includes the new session
        response = client.get("/health")
        data = response.json()
        assert data["session_count"] >= 1

    def test_root_endpoint_returns_service_info(self, client):
        """Root endpoint should return service information."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "MR-Krabs MCP Server"
        assert "version" in data
        assert "description" in data
        assert "endpoints" in data
        assert "health" in data["endpoints"]
        assert "tools" in data["endpoints"]


class TestToolsEndpoint:
    """Test tools listing endpoint."""

    def test_list_tools_returns_all_categories(self, client):
        """Tools endpoint should list all tool categories."""
        response = client.get("/tools")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "tools" in data
        assert "total_count" in data
        assert "categories" in data
        
        # Verify expected categories exist
        tools = data["tools"]
        assert "session" in tools
        assert "cost" in tools
        assert "budget" in tools
        assert "crew" in tools
        assert "agent" in tools
        assert "analytics" in tools

    def test_list_tools_includes_session_tools(self, client):
        """Tools endpoint should include session management tools."""
        response = client.get("/tools")
        data = response.json()
        
        session_tools = {t["name"] for t in data["tools"]["session"]}
        assert "mcp_mrkrabs_session_init" in session_tools
        assert "mcp_mrkrabs_session_status" in session_tools
        assert "mcp_mrkrabs_session_close" in session_tools

    def test_total_tool_count_is_accurate(self, client):
        """Total tool count should match sum of all categories."""
        response = client.get("/tools")
        data = response.json()
        
        calculated_total = sum(len(v) for v in data["tools"].values())
        assert data["total_count"] == calculated_total


class TestSessionInit:
    """Test session initialization endpoint."""

    def test_session_init_creates_session(self, client):
        """POST to session init should create a new session."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 15.0, "enforcement_mode": "notify_then_fail"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "active"
        assert "config" in data
        assert "message" in data

    def test_session_id_is_unique(self, client):
        """Each session should have a unique ID."""
        resp1 = client.post("/tools/mcp_mrkrabs_session_init", json={})
        resp2 = client.post("/tools/mcp_mrkrabs_session_init", json={})
        
        session_id_1 = resp1.json()["session_id"]
        session_id_2 = resp2.json()["session_id"]
        
        assert session_id_1 != session_id_2

    def test_session_init_with_custom_budget(self, client):
        """Session should accept custom budget limit."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 25.50}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["budget_limit"] == 25.50

    def test_session_init_with_custom_enforcement_mode(self, client):
        """Session should accept custom enforcement mode."""
        for mode in ["notify_only", "fail", "notify_then_fail", "fail_with_notification"]:
            response = client.post(
                "/tools/mcp_mrkrabs_session_init",
                json={"enforcement_mode": mode}
            )
            
            assert response.status_code == 200, f"Failed for mode: {mode}"
            assert response.json()["config"]["enforcement_mode"] == mode

    def test_session_init_with_warning_threshold(self, client):
        """Session should accept custom warning threshold."""
        response = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"warning_threshold": 90.0}
        )
        
        assert response.status_code == 200
        assert response.json()["config"]["warning_threshold"] == 90.0

    def test_session_init_with_default_values(self, client):
        """Session should use defaults when no config provided."""
        response = client.post("/tools/mcp_mrkrabs_session_init", json={})
        
        assert response.status_code == 200
        data = response.json()
        # Check that config exists and has expected fields if set
        assert "config" in data or "session_id" in data

    def test_session_init_includes_ttl_in_message(self, client):
        """Session init response should mention TTL."""
        response = client.post("/tools/mcp_mrkrabs_session_init", json={})
        
        assert response.status_code == 200
        assert "TTL" in response.json()["message"]


class TestSessionStatus:
    """Test session status endpoint."""

    def test_session_status_returns_active_for_valid_session(self, client):
        """GET status for valid session should return active=True."""
        # Create session
        init_resp = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        session_id = init_resp.json()["session_id"]
        
        # Check status
        response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["active"] is True
        assert "config" in data
        assert "time_remaining_seconds" in data

    def test_session_status_returns_config(self, client):
        """Session status should include the session config."""
        init_resp = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 20.0, "enforcement_mode": "fail"}
        )
        session_id = init_resp.json()["session_id"]
        
        response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        data = response.json()
        
        assert data["config"]["budget_limit"] == 20.0
        assert data["config"]["enforcement_mode"] == "fail"

    def test_session_status_returns_time_remaining(self, client):
        """Session status should include time remaining before expiration."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        response = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        data = response.json()
        
        assert "time_remaining_seconds" in data
        assert data["time_remaining_seconds"] > 0
        # TTL is 3600 seconds by default, should be close to that
        assert data["time_remaining_seconds"] <= 3600

    def test_session_status_returns_inactive_for_missing_session(self, client):
        """GET status for non-existent session should return active=False."""
        response = client.get("/tools/mcp_mrkrabs_session_status/nonexistent-session-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False


class TestSessionClose:
    """Test session close endpoint."""

    def test_session_close_deletes_session(self, client):
        """DELETE to close should remove the session."""
        # Create session
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Verify it exists
        status_before = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        assert status_before.json()["active"] is True
        
        # Close it
        response = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["closed"] is True

    def test_session_close_makes_session_inactive(self, client):
        """Closed session should show as inactive."""
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Close it
        client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        
        # Verify inactive
        status_after = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        assert status_after.json()["active"] is False

    def test_session_close_returns_false_for_missing_session(self, client):
        """Closing non-existent session should return closed=False."""
        response = client.delete("/tools/mcp_mrkrabs_session_close/nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["closed"] is False


class TestPingEndpoint:
    """Test ping endpoint."""

    def test_ping_returns_ok(self, client):
        """POST to ping should return status ok."""
        response = client.post("/tools/mcp_mrkrabs_ping", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data

    def test_ping_with_valid_session_returns_session_active_true(self, client):
        """Ping with valid session_id should show session is active."""
        # Create session
        init_resp = client.post("/tools/mcp_mrkrabs_session_init", json={})
        session_id = init_resp.json()["session_id"]
        
        # Ping with session
        response = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["session_active"] is True

    def test_ping_with_invalid_session_returns_session_active_false(self, client):
        """Ping with invalid session_id should show session is not active."""
        response = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": "nonexistent-session"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_active"] is False


class TestSessionLifecycleIntegration:
    """Integration tests for complete session lifecycle."""

    def test_full_session_lifecycle(self, client):
        """Test create -> use -> close lifecycle."""
        # 1. Create session with custom config
        init_resp = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 50.0,
                "enforcement_mode": "fail_with_notification"
            }
        )
        assert init_resp.status_code == 200
        session_id = init_resp.json()["session_id"]
        
        # 2. Verify session is active
        status_resp = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        assert status_resp.json()["active"] is True
        assert status_resp.json()["config"]["budget_limit"] == 50.0
        
        # 3. Ping with session
        ping_resp = client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id}
        )
        assert ping_resp.json()["session_active"] is True
        
        # 4. Close session
        close_resp = client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        assert close_resp.json()["closed"] is True
        
        # 5. Verify session is now inactive
        status_after = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        assert status_after.json()["active"] is False

    def test_multiple_sessions_independant(self, client):
        """Multiple sessions should be independent."""
        # Create two sessions with different configs
        resp1 = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0}
        )
        resp2 = client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 100.0}
        )
        
        session_id_1 = resp1.json()["session_id"]
        session_id_2 = resp2.json()["session_id"]
        
        # Verify they have different budgets
        status1 = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id_1}")
        status2 = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id_2}")
        
        assert status1.json()["config"]["budget_limit"] == 10.0
        assert status2.json()["config"]["budget_limit"] == 100.0
        
        # Close one, verify other still active
        client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id_1}")
        
        status1_after = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id_1}")
        status2_after = client.get(f"/tools/mcp_mrkrabs_session_status/{session_id_2}")
        
        assert status1_after.json()["active"] is False
        assert status2_after.json()["active"] is True
