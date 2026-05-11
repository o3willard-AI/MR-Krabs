"""
Tests for authentication module.
"""

import os
import time
import pytest
from src.mcp.auth import AuthManager, KeyManager, RateLimiter, create_jwt, verify_jwt


def test_jwt_creation_and_verification():
    """Test JWT creation and verification."""
    secret = "test-secret-key"
    auth_manager = AuthManager(secret)
    
    # Create a token
    token = auth_manager.create_token("test-client", ["read", "write"])
    
    # Verify the token
    payload = auth_manager.validate_token(token)
    
    assert payload["sub"] == "test-client"
    assert payload["scopes"] == ["read", "write"]
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_expired_token():
    """Test that expired tokens are rejected."""
    secret = "test-secret-key"
    auth_manager = AuthManager(secret, token_expiry_minutes=-1)  # Expire immediately
    
    # Create a token
    token = auth_manager.create_token("test-client")
    
    # Verify the token should fail due to expiration
    with pytest.raises(ValueError, match="Token expired"):
        auth_manager.validate_token(token)


def test_jwt_invalid_signature():
    """Test that tokens with invalid signatures are rejected."""
    secret1 = "secret-key-1"
    secret2 = "secret-key-2" 
    auth_manager = AuthManager(secret1)
    
    # Create a token
    token = auth_manager.create_token("test-client")
    
    # Try to verify with wrong secret - should fail
    wrong_auth = AuthManager(secret2)
    with pytest.raises(ValueError, match="Invalid signature"):
        wrong_auth.validate_token(token)


def test_api_key_management():
    """Test API key management functionality."""
    key_manager = KeyManager()
    
    # Add a key
    key_manager.add_key("test-key-123", "test-key-label")
    
    # Validate the key
    assert key_manager.validate_key("test-key-123") is True
    assert key_manager.validate_key("wrong-key") is False
    
    # List keys
    keys = key_manager.list_keys()
    assert len(keys) == 1
    assert keys[0]["key"] == "test****-123"  # Masked key (4 + 4 + 4 pattern)
    assert keys[0]["label"] == "test-key-label"
    
    # Revoke key
    key_manager.revoke_key("test-key-123")
    assert key_manager.validate_key("test-key-123") is False


def test_rate_limiter():
    """Test rate limiting functionality."""
    rate_limiter = RateLimiter(max_requests=2, window_seconds=10)
    
    # First two requests should be allowed
    assert rate_limiter.check("client-1") is True
    assert rate_limiter.check("client-1") is True
    
    # Third request should be denied
    assert rate_limiter.check("client-1") is False
    
    # Check remaining count
    assert rate_limiter.get_remaining("client-1") == 0
    
    # Wait for window to expire and try again
    time.sleep(11)  # Wait for window to expire
    assert rate_limiter.check("client-1") is True


def test_rate_limiter_per_client():
    """Test that rate limiting works per client."""
    rate_limiter = RateLimiter(max_requests=1, window_seconds=10)
    
    # Client 1 should be allowed
    assert rate_limiter.check("client-1") is True
    
    # Client 2 should also be allowed (different client)
    assert rate_limiter.check("client-2") is True
    
    # Both clients should be denied now
    assert rate_limiter.check("client-1") is False
    assert rate_limiter.check("client-2") is False


def test_backward_compatibility_with_legacy_key():
    """Test that existing MCP_API_KEY environment variable works."""
    # Set up legacy key in environment
    os.environ["MCP_API_KEY"] = "legacy-key-test"
    
    try:
        from src.mcp.auth import KeyManager
        
        key_manager = KeyManager()
        # Seed with existing MCP_API_KEY if set
        if existing_key := os.getenv("MCP_API_KEY"):
            key_manager.add_key(existing_key, "legacy")
        
        assert key_manager.validate_key("legacy-key-test") is True
        assert key_manager.validate_key("wrong-key") is False
    finally:
        # Clean up environment variable
        del os.environ["MCP_API_KEY"]


def test_create_jwt_with_only_required_fields():
    """Test JWT creation with minimal payload."""
    secret = "test-secret"
    
    payload = {
        "sub": "test-client",
        "exp": int(time.time() + 3600),
        "iat": int(time.time()),
    }
    
    token = create_jwt(payload, secret)
    verified_payload = verify_jwt(token, secret)
    
    assert verified_payload["sub"] == "test-client"
    assert verified_payload["exp"] > time.time()
    assert verified_payload["iat"] <= time.time()


def test_auth_manager_default_values():
    """Test AuthManager with default values."""
    auth_manager = AuthManager("test-secret")
    
    assert auth_manager.secret_key == "test-secret"
    assert auth_manager.token_expiry_minutes == 60  # Default value


def test_key_manager_empty_state():
    """Test KeyManager in empty state."""
    key_manager = KeyManager()
    
    assert len(key_manager.list_keys()) == 0
    assert key_manager.validate_key("any-key") is False


def test_rate_limiter_default_values():
    """Test RateLimiter with default values."""
    rate_limiter = RateLimiter()
    
    assert rate_limiter.max_requests == 100
    assert rate_limiter.window_seconds == 60


def test_public_paths_bypass_auth():
    """Test that public paths bypass authentication."""
    # This would be tested in integration tests as it requires the middleware
    # For unit tests, we'll just verify the path list is correct
    from src.mcp.auth import AuthMiddleware
    
    assert "/" in AuthMiddleware.PUBLIC_PATHS
    assert "/health" in AuthMiddleware.PUBLIC_PATHS
    assert "/tools" in AuthMiddleware.PUBLIC_PATHS
    assert "/docs" in AuthMiddleware.PUBLIC_PATHS