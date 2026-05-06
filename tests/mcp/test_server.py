"""
Unit tests for MR-Krabs MCP Server - FastAPI Application

Tests cover:
- Health check endpoint
- Session management endpoints
- Request/response models
- Authentication (when enabled)
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock

from src.mcp.server import app, session_manager


@pytest.fixture
async def test_client():
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    async def test_health_check_success(self, test_client):
        """Test successful health check."""
        response = await test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mr-krabs-mcp"
        assert "version" in data
        assert "session_count" in data
    
    async def test_root_endpoint(self, test_client):
        """Test root endpoint."""
        response = await test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "MR-Krabs MCP Server"
        assert "endpoints" in data


class TestListToolsEndpoint:
    """Test tools listing endpoint."""
    
    async def test_list_tools_success(self, test_client):
        """Test successful tool listing."""
        response = await test_client.get("/tools")
        
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "total_count" in data
        assert "categories" in data
        assert len(data["tools"]) > 0


class TestSessionInitEndpoint:
    """Test session initialization endpoint."""
    
    async def test_session_init_success(self, test_client):
        """Test successful session creation."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={
                "budget_limit": 15.0,
                "enforcement_mode": "notify_then_fail",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "active"
        assert data["config"]["budget_limit"] == 15.0
    
    async def test_session_init_defaults(self, test_client):
        """Test session creation with default values."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["budget_limit"] == 10.0  # Default
        assert data["config"]["enforcement_mode"] == "notify_then_fail"  # Default


class TestSessionStatusEndpoint:
    """Test session status endpoint."""
    
    async def test_session_status_active(self, test_client):
        """Test status of active session."""
        # First create a session
        init_response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"budget_limit": 10.0},
        )
        session_id = init_response.json()["session_id"]
        
        # Then check status
        response = await test_client.get(f"/tools/mcp_mrkrabs_session_status/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["active"] is True
        assert "config" in data
        assert "time_remaining_seconds" in data
    
    async def test_session_status_not_found(self, test_client):
        """Test status of non-existent session."""
        response = await test_client.get("/tools/mcp_mrkrabs_session_status/nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False


class TestSessionCloseEndpoint:
    """Test session close endpoint."""
    
    async def test_session_close_success(self, test_client):
        """Test successful session closure."""
        # First create a session
        init_response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
        )
        session_id = init_response.json()["session_id"]
        
        # Then close it
        response = await test_client.delete(f"/tools/mcp_mrkrabs_session_close/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["closed"] is True
    
    async def test_session_close_not_found(self, test_client):
        """Test closing non-existent session."""
        response = await test_client.delete("/tools/mcp_mrkrabs_session_close/nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["closed"] is False


class TestPingEndpoint:
    """Test ping endpoint."""
    
    async def test_ping_success(self, test_client):
        """Test successful ping."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_ping",
            json={},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "session_active" not in data or data["session_active"] is None
    
    async def test_ping_with_session(self, test_client):
        """Test ping with session_id."""
        # Create a session
        init_response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
        )
        session_id = init_response.json()["session_id"]
        
        # Ping with session
        response = await test_client.post(
            "/tools/mcp_mrkrabs_ping",
            json={"session_id": session_id},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["session_active"] is True


class TestAuthentication:
    """Test authentication endpoints."""
    
    @patch("os.getenv", return_value="test-api-key")
    async def test_auth_required(self, mock_env, test_client):
        """Test that auth is required when API key is set."""
        # This should fail without proper auth
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
        )
        
        assert response.status_code == 401
    
    @patch("os.getenv", return_value="test-api-key")
    async def test_auth_valid(self, mock_env, test_client):
        """Test successful auth with valid key."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
            headers={"Authorization": "Bearer test-api-key"},
        )
        
        assert response.status_code == 200
    
    @patch("os.getenv", return_value="test-api-key")
    async def test_auth_invalid(self, mock_env, test_client):
        """Test invalid auth with wrong key."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
            headers={"Authorization": "Bearer wrong-key"},
        )
        
        assert response.status_code == 403


class TestRequestValidation:
    """Test request validation."""
    
    async def test_session_init_invalid_enforcement_mode(self, test_client):
        """Test session init with invalid enforcement mode."""
        response = await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={"enforcement_mode": "invalid-mode"},
        )
        
        # Should fail validation or handle gracefully
        assert response.status_code in [422, 500]


class TestStartupShutdown:
    """Test startup and shutdown events."""
    
    @patch("structlog.get_logger")
    def test_startup_event(self, mock_get_logger):
        """Test startup event logs correctly."""
        from src.mcp import server
        
        # Trigger startup
        mock_log = MagicMock()
        mock_get_logger.return_value = mock_log
        
        result = server.startup_event()
        
        assert result is None  # Async function returns None


class TestSessionCountIntegration:
    """Integration tests for session counting."""
    
    async def test_session_count_increases(self, test_client):
        """Test that session count increases after creation."""
        # Get initial count
        response1 = await test_client.get("/health")
        initial_count = response1.json()["session_count"]
        
        # Create a session
        await test_client.post(
            "/tools/mcp_mrkrabs_session_init",
            json={},
        )
        
        # Verify count increased
        response2 = await test_client.get("/health")
        new_count = response2.json()["session_count"]
        
        assert new_count == initial_count + 1
