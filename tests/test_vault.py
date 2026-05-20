"""
Tests for Encrypted Vault Security Layer

This test suite validates the security features of the vault including:
- Encryption/decryption functionality
- Secure logging (sanitization)
- Audit trail generation
- Rate limiting
- Key management operations

Note: These tests use a MEMORY backend to avoid creating real encrypted files.
For production testing, use the encrypted backend with test keys only.
"""

import pytest
import os
import time
from unittest.mock import patch, MagicMock
from datetime import datetime
import json

# Import vault components
from src.core.vault import (
    Vault,
    EncryptedVault,
    MemoryVault,
    SecurityLogger,
    AuditLogger,
    RateLimiter,
    KeyNotFoundError,
    VaultBackendError,
    generate_master_key,
)


class TestVaultFactory:
    """Test vault factory methods."""
    
    def test_create_encrypted_vault(self):
        """Test creating encrypted vault instance."""
        master_key = generate_master_key()
        
        with patch('builtins.open'):  # Mock file operations
            vault = Vault.create(
                backend="encrypted",
                master_key=master_key
            )
        
        assert isinstance(vault, EncryptedVault)
        assert hasattr(vault, '_vault')
    
    def test_create_memory_vault(self):
        """Test creating memory vault instance."""
        vault = Vault.create(backend="memory")
        
        assert isinstance(vault, MemoryVault)
        assert "providers" in vault._vault
    
    def test_create_unknown_backend_raises_error(self):
        """Test that unknown backend raises ValueError."""
        with pytest.raises(ValueError):
            Vault.create(backend="unknown")


class TestEncryptedVault:
    """Test encrypted vault operations."""
    
    @pytest.fixture
    def memory_vault(self):
        """Create a memory vault for testing."""
        return MemoryVault()
    
    def test_add_provider_key(self, memory_vault):
        """Test adding provider API key to vault."""
        # Add OpenAI key
        memory_vault.add_provider_key("openai", "sk-test123")
        
        # Verify it's stored
        assert memory_vault.has_provider("openai")
    
    def test_get_provider_key(self, memory_vault):
        """Test retrieving provider API key from vault."""
        # Add key first
        memory_vault.add_provider_key("anthropic", "anthro_testkey")
        
        # Retrieve it
        api_key = memory_vault.get_provider_key("anthropic")
        
        assert api_key == "anthro_testkey"
    
    def test_get_nonexistent_key_raises_error(self, memory_vault):
        """Test that getting nonexistent key raises KeyNotFoundError."""
        with pytest.raises(KeyNotFoundError):
            memory_vault.get_provider_key("nonexistent_provider")
    
    def test_remove_provider_key(self, memory_vault):
        """Test removing provider key from vault."""
        # Add and then remove
        memory_vault.add_provider_key("openrouter", "or-test")
        assert memory_vault.has_provider("openrouter")
        
        memory_vault.remove_provider_key("openrouter")
        assert not memory_vault.has_provider("openrouter")
    
    def test_list_providers(self, memory_vault):
        """Test listing all providers in vault."""
        # Add multiple providers
        memory_vault.add_provider_key("openai", "sk-123")
        memory_vault.add_provider_key("anthropic", "anthro-456")
        memory_vault.add_provider_key("openrouter", "or-789")
        
        # List them
        providers = memory_vault.list_providers()
        
        assert len(providers) == 3
        assert "openai" in providers
        assert "anthropic" in providers
        assert "openrouter" in providers
    
    def test_provider_name_case_insensitive(self, memory_vault):
        """Test that provider names are case-insensitive."""
        # Add with uppercase
        memory_vault.add_provider_key("OPENAI", "sk-test")
        
        # Retrieve with lowercase
        api_key = memory_vault.get_provider_key("openai")
        
        assert api_key == "sk-test"
    
    def test_add_key_with_metadata(self, memory_vault):
        """Test adding provider key with metadata."""
        memory_vault.add_provider_key(
            "openai", 
            "sk-with-metadata",
            metadata={
                "rate_limit": 100,
                "description": "Test key for development"
            }
        )
        
        # Verify metadata stored (via vault internals)
        assert "openai" in memory_vault._vault["providers"]


class TestSecurityLogger:
    """Test security logger sanitization features."""
    
    @pytest.fixture
    def sec_logger(self):
        """Create a security logger instance."""
        import logging
        
        # Create mock base logger
        base_logger = MagicMock(spec=logging.Logger)
        return SecurityLogger(base_logger)
    
    def test_sanitize_removes_api_key_from_dict(self, sec_logger):
        """Test that API keys are removed from dictionary values."""
        data = {
            "provider": "openai",
            "api_key": "sk-real-key-123",
            "rate_limit": 100
        }
        
        sanitized = sec_logger._sanitize(data)
        
        assert sanitized["provider"] == "openai"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["rate_limit"] == 100
    
    def test_sanitize_removes_secret_from_dict(self, sec_logger):
        """Test that secrets are removed from dictionary values."""
        data = {
            "token": "secret_token_123",
            "user_id": "user_456"
        }
        
        sanitized = sec_logger._sanitize(data)
        
        assert sanitized["token"] == "***REDACTED***"
        assert sanitized["user_id"] == "user_456"  # Not sensitive
    
    def test_sanitize_detects_api_key_pattern(self, sec_logger):
        """Test that API key-like strings are detected."""
        api_key = "sk-this-is-a-real-looking-api-key-1234567890abcdef"
        
        sanitized = sec_logger._sanitize(api_key)
        
        assert sanitized == "***REDACTED***"
    
    def test_sanitize_allows_normal_strings(self, sec_logger):
        """Test that normal strings are not sanitized."""
        normal_text = "This is just a regular message"
        
        result = sec_logger._sanitize(normal_text)
        
        assert result == normal_text
    
    def test_sanitize_nested_dict(self, sec_logger):
        """Test sanitization of nested dictionaries."""
        data = {
            "config": {
                "api_key": "secret-key",
                "settings": {
                    "token": "another-secret"
                }
            }
        }
        
        sanitized = sec_logger._sanitize(data)
        
        assert sanitized["config"]["api_key"] == "***REDACTED***"
        assert sanitized["config"]["settings"]["token"] == "***REDACTED***"
    
    def test_sanitize_list_with_keys(self, sec_logger):
        """Test sanitization of lists containing keys."""
        data = [
            "normal_value",
            "sk-api-key-like-string-1234567890abcdef",
            {"secret": "password"}
        ]
        
        sanitized = sec_logger._sanitize(data)
        
        assert sanitized[0] == "normal_value"
        assert sanitized[1] == "***REDACTED***"
        assert sanitized[2]["secret"] == "***REDACTED***"


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a fresh rate limiter for testing."""
        return RateLimiter()
    
    def test_check_request_limit_passes_under_threshold(self, rate_limiter):
        """Test that requests under limit pass."""
        # First request should pass
        assert rate_limiter.check_request_limit("openai") is True
    
    def test_check_request_limit_fails_over_threshold(self, rate_limiter):
        """Test that requests over limit fail."""
        # Make 10 requests (at the limit)
        for i in range(10):
            assert rate_limiter.check_request_limit("openai") is True
        
        # 11th request should fail
        assert rate_limiter.check_request_limit("openai") is False
    
    def test_rate_limit_reset_after_second(self, rate_limiter):
        """Test that rate limit resets after one second."""
        # Exhaust the limit
        for i in range(10):
            rate_limiter.check_request_limit("test_provider")
        
        # Should fail now
        assert rate_limiter.check_request_limit("test_provider") is False
        
        # Wait for reset
        time.sleep(1.1)
        
        # Should pass again
        assert rate_limiter.check_request_limit("test_provider") is True
    
    def test_separate_providers_have_separate_limits(self, rate_limiter):
        """Test that different providers have independent limits."""
        # Exhaust openai limit
        for i in range(10):
            rate_limiter.check_request_limit("openai")
        
        assert rate_limiter.check_request_limit("openai") is False
        
        # Anthropic should still work
        assert rate_limiter.check_request_limit("anthropic") is True
    
    def test_budget_limit_check(self, rate_limiter):
        """Test budget limit checking."""
        # Under budget ($10)
        assert rate_limiter.check_budget_limit("openai", 10.0) is True
        
        # Over budget ($51 exceeds $50/hour limit)
        assert rate_limiter.check_budget_limit("openai", 51.0) is False


class TestAuditLogger:
    """Test audit logging functionality."""
    
    def test_log_access_creates_audit_entry(self, tmp_path):
        """Test that access logs are created."""
        audit_log_file = tmp_path / "audit.log"
        
        with patch('builtins.open', MagicMock()):
            audit_logger = AuditLogger(str(audit_log_file))
            
            # Mock the file handler to capture output
            captured_logs = []
            
            def mock_info(msg):
                captured_logs.append(msg)
            
            audit_logger.audit_logger.info = mock_info
            
            # Log an access event
            audit_logger.log_access(
                action="get_key",
                provider="openai",
                success=True
            )
            
            assert len(captured_logs) == 1
            log_entry = json.loads(captured_logs[0])
            
            assert log_entry["event_type"] == "vault_access"
            assert log_entry["action"] == "get_key"
            assert log_entry["provider"] == "openai"
            assert log_entry["success"] is True
    
    def test_log_security_event(self, tmp_path):
        """Test security event logging."""
        with patch('builtins.open', MagicMock()):
            audit_logger = AuditLogger(str(tmp_path / "audit.log"))
            
            captured_logs = []
            audit_logger.audit_logger.info = lambda msg: captured_logs.append(msg)
            
            # Log a security event
            audit_logger.log_security_event(
                event_type="key_removed",
                details={
                    "provider": "openai",
                    "reason": "rotation"
                }
            )
            
            assert len(captured_logs) == 1
            log_entry = json.loads(captured_logs[0])
            
            assert log_entry["event_type"] == "security_key_removed"
            assert log_entry["provider"] == "openai"


class TestVaultSecurity:
    """Test security features of the vault."""
    
    @pytest.fixture
    def memory_vault(self):
        """Create a memory vault for testing."""
        return MemoryVault()
    
    def test_audits_all_key_accesses(self, memory_vault):
        """Test that all key accesses are audited."""
        # Add a key
        memory_vault.add_provider_key("openai", "sk-test")
        
        # Get the audit log calls
        original_log = memory_vault.audit_logger.log_access
        audit_calls = []
        
        def track_call(*args, **kwargs):
            audit_calls.append(kwargs)
            return original_log(*args, **kwargs)
        
        with patch.object(memory_vault.audit_logger, 'log_access', side_effect=track_call):
            # Access the key
            memory_vault.get_provider_key("openai")
            
            # Should have been audited
            assert len(audit_calls) == 1
            assert audit_calls[0]["action"] == "get_key"
    
    def test_rate_limiting_applied_to_all_accesses(self, memory_vault):
        """Test that rate limiting is enforced."""
        memory_vault.add_provider_key("openai", "sk-test")
        
        # Make requests up to the limit
        for i in range(10):
            key = memory_vault.get_provider_key("openai")
            assert key == "sk-test"
        
        # Next request should be denied
        with pytest.raises(Exception):  # Rate limit error
            memory_vault.get_provider_key("openai")
    
    def test_logs_are_sanitized(self, memory_vault):
        """Test that logs don't contain API keys."""
        import io
        import sys
        
        # Capture log output
        log_capture = io.StringIO()
        
        # Get the base logger's handler
        original_handler = memory_vault.sec_logger.logger.handlers[0] if memory_vault.sec_logger.logger.handlers else None
        
        # Add a string handler to capture logs
        from logging import StreamHandler
        stream_handler = StreamHandler(log_capture)
        stream_handler.setFormatter(memory_vault.sec_logger.logger.handlers[0].formatter if original_handler and hasattr(original_handler, 'formatter') else None)
        memory_vault.sec_logger.logger.addHandler(stream_handler)
        
        # Add a key (this generates logs)
        memory_vault.add_provider_key("openai", "sk-super-secret-key-123")
        
        # Get the log output
        log_output = log_capture.getvalue()
        
        # Verify key is not in logs
        assert "sk-super-secret-key-123" not in log_output


class TestGenerateMasterKey:
    """Test master key generation."""
    
    def test_generate_master_key_format(self):
        """Test that generated keys are valid Fernet keys."""
        from cryptography.fernet import Fernet
        
        # Generate a key
        key = generate_master_key()
        
        # Should be able to create a Fernet instance with it
        fernet = Fernet(key.encode())
        
        assert fernet is not None
    
    def test_generate_master_key_length(self):
        """Test that generated keys have correct length."""
        key = generate_master_key()
        
        # Fernet keys are base64-encoded 32-byte keys
        # Base64 encoding of 32 bytes = 44 characters
        assert len(key) == 44
    
    def test_generate_master_keys_are_unique(self):
        """Test that generated keys are different each time."""
        key1 = generate_master_key()
        key2 = generate_master_key()
        
        assert key1 != key2


class TestVaultIntegration:
    """Integration tests for complete vault workflow."""
    
    def test_complete_provider_lifecycle(self):
        """Test complete provider lifecycle (add, get, remove)."""
        vault = MemoryVault()
        
        # Add provider
        vault.add_provider_key("openai", "sk-lifecycle-test")
        assert vault.has_provider("openai")
        
        # Retrieve key
        key = vault.get_provider_key("openai")
        assert key == "sk-lifecycle-test"
        
        # List providers
        providers = vault.list_providers()
        assert "openai" in providers
        
        # Remove provider
        vault.remove_provider_key("openai")
        assert not vault.has_provider("openai")
        
        # Verify removal
        with pytest.raises(KeyNotFoundError):
            vault.get_provider_key("openai")
    
    def test_multiple_providers(self):
        """Test managing multiple providers."""
        vault = MemoryVault()
        
        # Add multiple providers
        vault.add_provider_key("openai", "sk-openai-key")
        vault.add_provider_key("anthropic", "anthropic-key")
        vault.add_provider_key("openrouter", "or-openrouter-key")
        
        # Verify all are accessible
        assert vault.get_provider_key("openai") == "sk-openai-key"
        assert vault.get_provider_key("anthropic") == "anthropic-key"
        assert vault.get_provider_key("openrouter") == "or-openrouter-key"
        
        # List should show all three
        providers = vault.list_providers()
        assert len(providers) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
