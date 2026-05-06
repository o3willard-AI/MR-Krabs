"""
Unit tests for MR-Krabs MCP Server - Session Manager

Tests cover:
- Session creation and retrieval
- TTL-based expiration
- Thread-safe concurrent access
- Configuration management
"""

import pytest
import time
import threading
from unittest.mock import patch

from src.mcp.session_manager import SessionManager, SessionConfig


class TestSessionConfig:
    """Test SessionConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SessionConfig(session_id="test-123")
        
        assert config.session_id == "test-123"
        assert config.budget_limit == 10.0
        assert config.enforcement_mode == "notify_then_fail"
        assert config.warning_threshold == 80.0
        assert config.default_tier == "L0"
        assert config.models == ["google/gemma-7b-it"]
        assert config.ttl_seconds == 3600
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = SessionConfig(
            session_id="custom-456",
            budget_limit=25.0,
            enforcement_mode="fail",
            warning_threshold=90.0,
            default_tier="L1",
            models=["model-a", "model-b"],
            ttl_seconds=7200,
        )
        
        assert config.budget_limit == 25.0
        assert config.enforcement_mode == "fail"
        assert config.warning_threshold == 90.0
        assert config.default_tier == "L1"
        assert config.models == ["model-a", "model-b"]
        assert config.ttl_seconds == 7200
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = SessionConfig(
            session_id="test-789",
            budget_limit=15.0,
            enforcement_mode="notify_only",
        )
        
        data = config.to_dict()
        
        assert data["session_id"] == "test-789"
        assert data["budget_limit"] == 15.0
        assert data["enforcement_mode"] == "notify_only"
        assert "created_at" in data
        assert "last_accessed" in data
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "session_id": "dict-123",
            "budget_limit": 20.0,
            "enforcement_mode": "fail_with_notification",
            "warning_threshold": 85.0,
            "default_tier": "L2",
            "models": ["model-x"],
        }
        
        config = SessionConfig.from_dict(data)
        
        assert config.session_id == "dict-123"
        assert config.budget_limit == 20.0
        assert config.enforcement_mode == "fail_with_notification"
        assert config.warning_threshold == 85.0
        assert config.default_tier == "L2"
        assert config.models == ["model-x"]
    
    def test_from_dict_defaults(self):
        """Test creation from dictionary with defaults."""
        data = {"session_id": "partial-456"}
        
        config = SessionConfig.from_dict(data)
        
        assert config.session_id == "partial-456"
        assert config.budget_limit == 10.0  # Default
        assert config.enforcement_mode == "notify_then_fail"  # Default
    
    def test_is_expired_not_expired(self):
        """Test expiration check when not expired."""
        with patch("time.time", return_value=1000):
            config = SessionConfig(
                session_id="not-expired",
                created_at=1000,
                last_accessed=1000,
                ttl_seconds=3600,
            )
        
        with patch("time.time", return_value=2000):  # 1000 seconds later
            assert not config.is_expired()
    
    def test_is_expired_expired(self):
        """Test expiration check when expired."""
        with patch("time.time", return_value=1000):
            config = SessionConfig(
                session_id="expired",
                created_at=1000,
                last_accessed=1000,
                ttl_seconds=3600,
            )
        
        with patch("time.time", return_value=5000):  # 4000 seconds later (> TTL)
            assert config.is_expired()


class TestSessionManager:
    """Test SessionManager class."""
    
    def test_create_session_default(self):
        """Test session creation with default config."""
        manager = SessionManager(ttl_seconds=3600)
        
        session_id = manager.create_session()
        
        assert session_id.startswith("session-")
        assert len(session_id) == 17  # "session-" + 8 hex chars
        
        # Verify session was stored
        session = manager.get_session(session_id)
        assert session is not None
        assert session.session_id == session_id
    
    def test_create_session_with_config(self):
        """Test session creation with custom config."""
        manager = SessionManager()
        
        config = {
            "budget_limit": 25.0,
            "enforcement_mode": "fail",
            "models": ["model-a", "model-b"],
        }
        
        session_id = manager.create_session(config=config)
        session = manager.get_session(session_id)
        
        assert session.budget_limit == 25.0
        assert session.enforcement_mode == "fail"
        assert session.models == ["model-a", "model-b"]
    
    def test_get_nonexistent_session(self):
        """Test retrieval of non-existent session."""
        manager = SessionManager()
        
        session = manager.get_session("nonexistent")
        
        assert session is None
    
    def test_delete_session(self):
        """Test session deletion."""
        manager = SessionManager()
        
        session_id = manager.create_session()
        assert manager.get_session(session_id) is not None
        
        result = manager.delete_session(session_id)
        
        assert result is True
        assert manager.get_session(session_id) is None
    
    def test_delete_nonexistent_session(self):
        """Test deletion of non-existent session."""
        manager = SessionManager()
        
        result = manager.delete_session("nonexistent")
        
        assert result is False
    
    def test_session_expiration(self):
        """Test automatic session expiration based on TTL."""
        # Create manager with short TTL
        manager = SessionManager(ttl_seconds=1)
        
        # Mock time to create session at t=0
        with patch("time.time", return_value=1000):
            session_id = manager.create_session()
        
        # Verify session exists at t=0
        with patch("time.time", return_value=1000):
            assert manager.get_session(session_id) is not None
        
        # Verify session expires after TTL (t=2, > 1 second TTL)
        with patch("time.time", return_value=1002):
            assert manager.get_session(session_id) is None
    
    def test_session_auto_cleanup_on_access(self):
        """Test that expired sessions are cleaned up on access."""
        manager = SessionManager(ttl_seconds=1)
        
        with patch("time.time", return_value=1000):
            session_id = manager.create_session()
        
        # Access at t=2 (expired) - should auto-remove
        with patch("time.time", return_value=1002):
            session = manager.get_session(session_id)
            assert session is None
        
        # Verify it's actually removed from storage
        assert session_id not in manager._sessions
    
    def test_list_sessions(self):
        """Test listing all active sessions."""
        manager = SessionManager(ttl_seconds=3600)
        
        with patch("time.time", return_value=1000):
            id1 = manager.create_session({"budget_limit": 10.0})
            id2 = manager.create_session({"budget_limit": 20.0})
        
        sessions = manager.list_sessions()
        
        assert len(sessions) == 2
        session_ids = [s.session_id for s in sessions]
        assert id1 in session_ids
        assert id2 in session_ids
    
    def test_list_sessions_filters_expired(self):
        """Test that list_sessions filters out expired sessions."""
        manager = SessionManager(ttl_seconds=1)
        
        with patch("time.time", return_value=1000):
            id1 = manager.create_session()  # Will expire
            id2 = manager.create_session()  # Will expire
        
        # Both should be listed at t=1000
        with patch("time.time", return_value=1000):
            assert len(manager.list_sessions()) == 2
        
        # Neither should be listed at t=1002 (expired)
        with patch("time.time", return_value=1002):
            sessions = manager.list_sessions()
            assert len(sessions) == 0
    
    def test_cleanup_expired(self):
        """Test explicit cleanup of expired sessions."""
        manager = SessionManager(ttl_seconds=1)
        
        with patch("time.time", return_value=1000):
            manager.create_session()
            manager.create_session()
        
        # Clean up at t=1002
        with patch("time.time", return_value=1002):
            count = manager.cleanup_expired()
        
        assert count == 2
    
    def test_get_session_count(self):
        """Test getting active session count."""
        manager = SessionManager(ttl_seconds=3600)
        
        with patch("time.time", return_value=1000):
            manager.create_session()
            manager.create_session()
            manager.create_session()
        
        count = manager.get_session_count()
        
        assert count == 3
    
    def test_get_session_updates_last_accessed(self):
        """Test that accessing a session updates last_accessed timestamp."""
        manager = SessionManager(ttl_seconds=3600)
        
        with patch("time.time", return_value=1000):
            session_id = manager.create_session()
        
        # Access at t=2000
        with patch("time.time", return_value=2000):
            session = manager.get_session(session_id)
        
        assert session.last_accessed == 2000
    
    def test_concurrent_session_creation(self):
        """Test thread-safe concurrent session creation."""
        manager = SessionManager()
        session_ids = []
        lock = threading.Lock()
        
        def create_sessions(count):
            for _ in range(count):
                session_id = manager.create_session()
                with lock:
                    session_ids.append(session_id)
        
        # Create 10 threads, each creating 10 sessions
        threads = [threading.Thread(target=create_sessions, args=(10,)) 
                  for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify all sessions are unique and stored
        assert len(session_ids) == 100
        assert len(set(session_ids)) == 100  # All unique
        
        for session_id in session_ids:
            assert manager.get_session(session_id) is not None


class TestSessionManagerEnvironment:
    """Test SessionManager with environment variables."""
    
    def test_default_ttl_from_env(self):
        """Test TTL from environment variable."""
        with patch("os.getenv", return_value="7200"):
            manager = SessionManager()
        
        assert manager.ttl_seconds == 7200
    
    def test_constructor_override_env(self):
        """Test constructor parameter overrides environment."""
        with patch("os.getenv", return_value="7200"):
            manager = SessionManager(ttl_seconds=1800)
        
        assert manager.ttl_seconds == 1800
