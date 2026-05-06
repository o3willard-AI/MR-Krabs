"""
Session Management for MR-Krabs MCP Server

Implements stateful session management with TTL-based expiration and concurrent access support.
Supports both stateful (recommended) and stateless fallback modes.

Usage:
    # Stateful mode
    session_id = session_manager.create_session(config={"budget": 10.0})
    
    # Retrieve and use session
    session = session_manager.get_session(session_id)
    
    # Clean up
    session_manager.delete_session(session_id)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import uuid
import time
import threading
import os


@dataclass
class SessionConfig:
    """Configuration for an MCP session."""
    
    session_id: str
    budget_limit: Optional[float] = 10.0  # Default $10/day
    enforcement_mode: str = "notify_then_fail"
    warning_threshold: float = 80.0  # Percent
    default_tier: str = "L0"
    models: list[str] = field(default_factory=lambda: ["google/gemma-7b-it"])
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    ttl_seconds: int = 3600  # Default 1 hour
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session config to dictionary."""
        return {
            "session_id": self.session_id,
            "budget_limit": self.budget_limit,
            "enforcement_mode": self.enforcement_mode,
            "warning_threshold": self.warning_threshold,
            "default_tier": self.default_tier,
            "models": self.models,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "ttl_seconds": self.ttl_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionConfig":
        """Create SessionConfig from dictionary."""
        return cls(
            session_id=data.get("session_id", f"session-{uuid.uuid4().hex[:8]}"),
            budget_limit=data.get("budget_limit", 10.0),
            enforcement_mode=data.get("enforcement_mode", "notify_then_fail"),
            warning_threshold=data.get("warning_threshold", 80.0),
            default_tier=data.get("default_tier", "L0"),
            models=data.get("models", ["google/gemma-7b-it"]),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            ttl_seconds=data.get("ttl_seconds", 3600),
        )
    
    def is_expired(self) -> bool:
        """Check if session has expired based on TTL."""
        return (time.time() - self.last_accessed) > self.ttl_seconds


class SessionManager:
    """
    Manages MCP sessions with thread-safe operations and TTL-based expiration.
    
    Features:
    - Thread-safe session storage
    - Automatic session expiration (TTL)
    - Concurrent session support
    - Optional config loading from TOML
    
    Environment Variables:
        SESSION_TTL: Session time-to-live in seconds (default: 3600)
    """
    
    def __init__(self, ttl_seconds: Optional[int] = None):
        """
        Initialize session manager.
        
        Args:
            ttl_seconds: Default TTL for sessions in seconds. 
                        Overrides SESSION_TTL env var if provided.
        """
        self.ttl_seconds = ttl_seconds or int(os.getenv("SESSION_TTL", "3600"))
        self._sessions: Dict[str, SessionConfig] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread safety
    
    def create_session(
        self, 
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new session with optional configuration.
        
        Args:
            config: Optional configuration dictionary. If None, uses defaults.
                   Can include: budget_limit, enforcement_mode, warning_threshold,
                               default_tier, models, ttl_seconds
        
        Returns:
            session_id: Unique identifier for the created session
        """
        with self._lock:
            # Generate unique session ID
            session_id = f"session-{uuid.uuid4().hex[:8]}"
            
            # Create config with overrides
            if config:
                session_config = SessionConfig(
                    session_id=session_id,
                    budget_limit=config.get("budget_limit", 10.0),
                    enforcement_mode=config.get("enforcement_mode", "notify_then_fail"),
                    warning_threshold=config.get("warning_threshold", 80.0),
                    default_tier=config.get("default_tier", "L0"),
                    models=config.get("models", ["google/gemma-7b-it"]),
                    ttl_seconds=config.get("ttl_seconds", self.ttl_seconds),
                )
            else:
                session_config = SessionConfig(session_id=session_id)
            
            # Store session
            self._sessions[session_id] = session_config
            
            return session_id
    
    def get_session(
        self, 
        session_id: str
    ) -> Optional[SessionConfig]:
        """
        Retrieve a session by ID.
        
        Args:
            session_id: The session identifier
        
        Returns:
            SessionConfig if session exists and not expired, None otherwise
        """
        with self._lock:
            session = self._sessions.get(session_id)
            
            if not session:
                return None
            
            # Check if session has expired
            if session.is_expired():
                # Clean up expired session
                del self._sessions[session_id]
                return None
            
            # Update last accessed time
            session.last_accessed = time.time()
            
            return session
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: The session identifier to delete
        
        Returns:
            True if session was deleted, False if it didn't exist
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def list_sessions(self) -> list[SessionConfig]:
        """
        List all active sessions.
        
        Returns:
            List of SessionConfig objects for all non-expired sessions
        """
        with self._lock:
            # Filter out expired sessions
            active_sessions = []
            expired_ids = []
            
            for session_id, session in self._sessions.items():
                if session.is_expired():
                    expired_ids.append(session_id)
                else:
                    active_sessions.append(session)
            
            # Clean up expired sessions
            for session_id in expired_ids:
                del self._sessions[session_id]
            
            return active_sessions
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.
        
        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired_count = 0
            
            for session_id in list(self._sessions.keys()):
                if self._sessions[session_id].is_expired():
                    del self._sessions[session_id]
                    expired_count += 1
            
            return expired_count
    
    def get_session_count(self) -> int:
        """Get count of active (non-expired) sessions."""
        with self._lock:
            return sum(1 for s in self._sessions.values() if not s.is_expired())
