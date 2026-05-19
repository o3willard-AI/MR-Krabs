"""Phase 3: Bearer authentication tests."""

import os
import pytest
from fastapi.testclient import TestClient
from src.mcp.server import app
from src.mcp.auth import BearerAuthMiddleware, create_auth_middleware


@pytest.fixture
def auth_enabled_client(monkeypatch):
    """Test client with Bearer auth enabled."""
    monkeypatch.setenv("MCP_BEARER_TOKEN", "test-token-123")
    monkeypatch.setenv("MCP_API_KEY", "test-api-key-456")
    monkeypatch.setenv("MRKRABS_ENABLE_BEARER_AUTH", "true")
    
    # Re-import to pick up env changes
    import importlib
    import src.mcp.server as server_module
    importlib.reload(server_module)
    
    return TestClient(server_module.app)


class TestBearerAuth:
    def test_health_bypasses_auth(self, auth_enabled_client):
        response = auth_enabled_client.get("/health")
        assert response.status_code == 200
    
    def test_metrics_bypasses_auth(self, auth_enabled_client):
        response = auth_enabled_client.get("/metrics")
        # 503 means metrics adapter not initialized, but auth was bypassed
        assert response.status_code in (200, 503, 404)
    
    def test_ready_bypasses_auth(self, auth_enabled_client):
        """Test that /ready endpoint is public."""
        response = auth_enabled_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
    
    def test_protected_endpoint_requires_auth(self, auth_enabled_client):
        response = auth_enabled_client.get("/tools")
        assert response.status_code == 401
    
    def test_valid_bearer_token_access(self, auth_enabled_client):
        response = auth_enabled_client.get(
            "/tools",
            headers={"Authorization": "Bearer test-token-123"}
        )
        assert response.status_code == 200
    
    def test_invalid_bearer_token_rejected(self, auth_enabled_client):
        response = auth_enabled_client.get(
            "/tools",
            headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401
    
    def test_valid_api_key_access(self, auth_enabled_client):
        response = auth_enabled_client.get(
            "/tools",
            headers={"X-API-Key": "test-api-key-456"}
        )
        assert response.status_code == 200
    
    def test_invalid_api_key_rejected(self, auth_enabled_client):
        response = auth_enabled_client.get(
            "/tools",
            headers={"X-API-Key": "wrong-api-key"}
        )
        assert response.status_code == 401
    
    def test_missing_auth_header_rejected(self, auth_enabled_client):
        """Test that missing Authorization header is rejected."""
        response = auth_enabled_client.get("/tools")
        assert response.status_code == 401


class TestBearerAuthDisabled:
    """When auth is disabled, all endpoints should be accessible."""
    
    @pytest.fixture
    def client_no_auth(self, monkeypatch):
        monkeypatch.setenv("MRKRABS_ENABLE_BEARER_AUTH", "false")
        import importlib
        import src.mcp.server as server_module
        importlib.reload(server_module)
        return TestClient(server_module.app)
    
    def test_protected_endpoint_no_auth(self, client_no_auth):
        response = client_no_auth.get("/tools")
        assert response.status_code == 200


class TestBearerAuthMiddlewareClass:
    def test_public_paths(self):
        middleware = BearerAuthMiddleware(None, enabled=True)
        assert "/health" in middleware.PUBLIC_PATHS
        assert "/metrics" in middleware.PUBLIC_PATHS
        assert "/ready" in middleware.PUBLIC_PATHS
    
    def test_disabled_bypasses_all(self):
        middleware = BearerAuthMiddleware(None, enabled=False)
        assert middleware.enabled is False
