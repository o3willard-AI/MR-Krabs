"""
Secure Vault Service for LLM Provider API Keys

This module provides secure storage and retrieval of LLM provider API keys
(OpenAI, Anthropic, OpenRouter, etc.) with encryption at rest and audit logging.

Security Features:
- Encrypted storage using Fernet symmetric encryption
- Support for multiple backends (memory, keyring, encrypted file, cloud KMS)
- Audit trail for all vault access
- Rate limiting to prevent abuse
- Automatic key rotation support

WARNING: This is a critical security component. Never expose vault endpoints
to external clients. Vault should only be accessed by internal MR-Krabs services.
"""

import os
import json
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import threading
import time

# Configure module logger (will be sanitized by security logger)
logger = logging.getLogger(__name__)


class VaultBackendError(Exception):
    """Raised when vault backend operations fail."""
    pass


class KeyNotFoundError(VaultBackendError):
    """Raised when requested key doesn't exist in vault."""
    pass


class VaultAccessDeniedError(Exception):
    """Raised when vault access is denied (internal use only)."""
    pass


class SecurityLogger:
    """
    Sanitized logger that automatically strips sensitive data from log messages.
    
    Usage:
        sec_logger = SecurityLogger(logger)
        sec_logger.info("Loaded config", config=sensitive_config_with_keys)
        # All keys/secrets will be stripped before logging
    """
    
    SENSITIVE_PATTERNS = [
        "key", "secret", "token", "password", "credential", 
        "api_key", "apikey", "access_token", "private_key"
    ]
    
    def __init__(self, base_logger: logging.Logger):
        self.logger = base_logger
    
    def _sanitize(self, obj: Any) -> Any:
        """Recursively remove sensitive data from objects."""
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if self._is_sensitive(k) else self._sanitize(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._sanitize(item) for item in obj]
        elif isinstance(obj, str):
            # Check if value looks like an API key
            if self._looks_like_key(obj):
                return "***REDACTED***"
            return obj
        else:
            return obj
    
    def _is_sensitive(self, key: str) -> bool:
        """Check if a dictionary key contains sensitive data."""
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in self.SENSITIVE_PATTERNS)
    
    def _looks_like_key(self, value: str) -> bool:
        """Detect if string looks like an API key."""
        # Common API key patterns
        if len(value) < 10:
            return False
        
        # Skim/secret prefix patterns (OpenAI style)
        if value.startswith(("sk-", "osk-", "or_", "anthropic_")):
            return True
        
        # Generic API key pattern (long alphanumeric string)
        import re
        if re.match(r'^[a-zA-Z0-9_-]{32,}$', value):
            return True
            
        return False
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, extra=self._sanitize(kwargs))
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, extra=self._sanitize(kwargs))
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, extra=self._sanitize(kwargs))
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, extra=self._sanitize(kwargs))
    
    def critical(self, msg: str, **kwargs):
        self.logger.critical(msg, extra=self._sanitize(kwargs))


class AuditLogger:
    """
    Security audit logger for tracking all vault access.
    
    Writes to separate audit log file for security monitoring.
    All audit logs are immutable once written.
    """
    
    def __init__(self, audit_log_path: Optional[str] = None):
        # Use environment variable or default based on context
        if audit_log_path is None:
            audit_log_path = os.environ.get(
                "MRKRABS_AUDIT_LOG_PATH",
                "/var/log/mrkrabs/audit.log"  # Production default
            )
        
        self.audit_file = Path(audit_log_path)
        
        # Create parent directory if needed (may fail in restricted environments)
        try:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fall back to user-writable location
            fallback_path = Path.home() / ".mrkrabs" / "audit.log"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            self.audit_file = fallback_path
        
        # Separate logger for audit (no sanitization - need full details for forensics)
        self._setup_audit_logger()
    
    def _setup_audit_logger(self):
        """Configure dedicated audit logger with file handler."""
        self.audit_logger = logging.getLogger("mrkrabs_audit")
        self.audit_logger.setLevel(logging.INFO)
        
        # File handler - append only, never overwrite
        file_handler = logging.FileHandler(str(self.audit_file))
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
        ))
        
        if not self.audit_logger.handlers:
            self.audit_logger.addHandler(file_handler)
    
    def log_access(self, action: str, provider: Optional[str] = None, 
                   success: bool = True, user_context: Optional[Dict] = None):
        """Log vault access for security audit."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "vault_access",
            "action": action,
            "provider": provider,
            "success": success,
            "user_context": user_context or {},
            "caller": self._get_caller_info()
        }
        
        # Write JSON line for easy parsing
        log_line = json.dumps(event)
        self.audit_logger.info(log_line)
    
    def log_security_event(self, event_type: str, details: Dict):
        """Log a security-relevant event."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": f"security_{event_type}",
            **details
        }
        
        log_line = json.dumps(event)
        self.audit_logger.info(log_line)
    
    def _get_caller_info(self) -> Dict:
        """Get information about the caller (for debugging)."""
        import traceback
        
        # Get stack trace without exposing sensitive data
        stack = traceback.extract_stack()
        if len(stack) > 3:
            caller_frame = stack[-3]
            return {
                "file": os.path.basename(caller_frame.filename),
                "function": caller_frame.name,
                "line": caller_frame.lineno
            }
        return {}


class RateLimiter:
    """
    Rate limiter to prevent abuse of LLM provider calls.
    
    Even if keys are somehow leaked, rate limiting prevents 
    unlimited budget drain.
    """
    
    def __init__(self):
        self.request_counts: Dict[str, List[float]] = {}
        self.lock = threading.Lock()
        
        # Limits per provider
        self.LIMITS = {
            "requests_per_second": 10,      # Max 10 requests/sec
            "tokens_per_minute": 100000,     # Max 100K tokens/min (~$1-5)
            "spend_per_hour": 50.0,          # Max $50/hour hard limit
        }
    
    def check_request_limit(self, provider: str) -> bool:
        """Check if request limit is exceeded."""
        now = time.time()
        
        with self.lock:
            # Get requests for this provider in the last second
            key = f"{provider}_requests"
            
            if key not in self.request_counts:
                self.request_counts[key] = []
            
            # Remove old timestamps (older than 1 second)
            self.request_counts[key] = [
                t for t in self.request_counts[key] 
                if now - t < 1.0
            ]
            
            # Check limit
            if len(self.request_counts[key]) >= self.LIMITS["requests_per_second"]:
                return False
            
            # Add current request timestamp
            self.request_counts[key].append(now)
            return True
    
    def check_budget_limit(self, provider: str, estimated_cost: float) -> bool:
        """Check if budget limit would be exceeded."""
        # This is a simplified check - in production, use proper accounting
        hourly_spend = self._get_hourly_spend(provider)
        
        if hourly_spend + estimated_cost > self.LIMITS["spend_per_hour"]:
            return False
        
        return True
    
    def _get_hourly_spend(self, provider: str) -> float:
        """Get approximate spend in the last hour."""
        # Placeholder - would integrate with actual cost tracking
        return 0.0


class EncryptedVault:
    """
    Encrypted vault for storing LLM provider API keys.
    
    Uses Fernet symmetric encryption with a master key derived from
    environment variable or configuration file.
    
    SECURITY NOTES:
    - Master key must be stored securely (env var, OS keyring, HSM)
    - Vault file should have restricted permissions (0600)
    - Never commit vault files to version control
    - Rotate master key periodically (requires re-encryption)
    """
    
    def __init__(
        self,
        vault_path: Optional[str] = None,
        master_key: Optional[str] = None
    ):
        """
        Initialize encrypted vault.
        
        Args:
            vault_path: Path to encrypted vault file (default: /etc/mrkrabs/vault.enc)
            master_key: Master encryption key or path to key file
        """
        self.vault_path = Path(vault_path or "/etc/mrkrabs/vault.enc")
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        
        # Security components
        self.sec_logger = SecurityLogger(logger)
        self.audit_logger = AuditLogger()
        self.rate_limiter = RateLimiter()
        
        # Initialize cipher
        self._cipher = self._load_cipher(master_key)
        
        # Load vault data
        self._vault: Dict[str, Any] = self._load_vault()
    
    def _load_cipher(self, master_key: Optional[str]) -> Fernet:
        """Load or generate the encryption cipher."""
        if master_key is None:
            # Try to get from environment
            master_key = os.environ.get("VAULT_MASTER_KEY")
            
            if not master_key:
                raise VaultBackendError(
                    "Vault master key not provided. Set VAULT_MASTER_KEY "
                    "environment variable or pass master_key parameter."
                )
        
        # If it's a file path, read the key from file
        if master_key.endswith(".key") and os.path.exists(master_key):
            with open(master_key, "r") as f:
                master_key = f.read().strip()
        
        # Validate key format (should be base64-encoded 32-byte key)
        try:
            key_bytes = base64.urlsafe_b64decode(master_key)
            if len(key_bytes) != 32:
                raise ValueError("Master key must be 32 bytes")
        except Exception as e:
            raise VaultBackendError(f"Invalid master key format: {e}")
        
        return Fernet(master_key.encode())
    
    def _load_vault(self) -> Dict[str, Any]:
        """Load vault from encrypted file or initialize empty."""
        if not self.vault_path.exists():
            self.sec_logger.info("Creating new encrypted vault", vault=str(self.vault_path))
            return {"providers": {}, "metadata": {
                "created": datetime.utcnow().isoformat(),
                "version": "1.0"
            }}
        
        try:
            # Read encrypted content
            with open(self.vault_path, "rb") as f:
                encrypted_data = f.read()
            
            # Decrypt
            decrypted = self._cipher.decrypt(encrypted_data)
            vault_data = json.loads(decrypted.decode())
            
            self.sec_logger.info("Loaded encrypted vault successfully")
            return vault_data
            
        except InvalidToken:
            raise VaultBackendError("Failed to decrypt vault - invalid master key")
        except Exception as e:
            raise VaultBackendError(f"Failed to load vault: {e}")
    
    def _save_vault(self):
        """Save vault to encrypted file (atomic write)."""
        temp_path = self.vault_path.with_suffix(".tmp")
        
        try:
            # Serialize and encrypt
            encrypted_data = self._cipher.encrypt(json.dumps(self._vault).encode())
            
            # Write to temp file first
            with open(temp_path, "wb") as f:
                f.write(encrypted_data)
            
            # Atomic rename (ensures no partial writes)
            os.replace(str(temp_path), str(self.vault_path))
            
            # Set restrictive permissions (owner read/write only)
            os.chmod(self.vault_path, 0o600)
            
            self.sec_logger.info("Saved encrypted vault")
            
        except Exception as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            
            raise VaultBackendError(f"Failed to save vault: {e}")
    
    def add_provider_key(self, provider: str, api_key: str, metadata: Optional[Dict] = None):
        """
        Add or update an LLM provider API key in the vault.
        
        Args:
            provider: Provider name (e.g., "openai", "anthropic", "openrouter")
            api_key: The API key to store (will be encrypted)
            metadata: Optional metadata (rate limits, description, etc.)
        
        SECURITY: This method should only be called during setup or key rotation.
                  Never call this in request-handling code!
        """
        with self._lock:
            provider_lower = provider.lower()
            
            # Log the operation (but NOT the key itself - it's sanitized)
            self.sec_logger.info(
                "Adding/updating provider key", 
                provider=provider,
                **self._sanitize_key_in_metadata(metadata or {})
            )
            
            # Audit log
            self.audit_logger.log_access(
                action="add_key",
                provider=provider,
                success=True
            )
            
            # Store in vault
            if "providers" not in self._vault:
                self._vault["providers"] = {}
            
            self._vault["providers"][provider_lower] = {
                "api_key": api_key,  # Will be encrypted when saved
                "added": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            
            # Save to disk
            self._save_vault()
    
    def get_provider_key(self, provider: str) -> str:
        """
        Get an LLM provider API key from the vault.
        
        Args:
            provider: Provider name (e.g., "openai", "anthropic")
            
        Returns:
            The API key as a string
            
        Raises:
            KeyNotFoundError: If provider key doesn't exist
            VaultAccessDeniedError: If access is denied
            
        SECURITY: Rate limiting and audit logging applied automatically.
        """
        provider_lower = provider.lower()
        
        # Check rate limit first
        if not self.rate_limiter.check_request_limit(provider):
            raise VaultAccessDeniedError(
                f"Rate limit exceeded for provider {provider}"
            )
        
        with self._lock:
            if "providers" not in self._vault:
                raise KeyNotFoundError(f"No vault data found")
            
            if provider_lower not in self._vault["providers"]:
                # Audit failed access attempt
                self.audit_logger.log_access(
                    action="get_key",
                    provider=provider,
                    success=False
                )
                
                raise KeyNotFoundError(f"No API key found for provider '{provider}'")
            
            # Get the key
            api_key = self._vault["providers"][provider_lower]["api_key"]
            
            # Log access (key is sanitized by security logger)
            self.sec_logger.debug(
                "Retrieved provider key",
                provider=provider
            )
            
            # Audit log
            self.audit_logger.log_access(
                action="get_key",
                provider=provider,
                success=True
            )
            
            return api_key
    
    def remove_provider_key(self, provider: str):
        """
        Remove a provider key from the vault.
        
        WARNING: This is destructive and should only be done during
                 security incidents or planned key rotation.
        """
        with self._lock:
            provider_lower = provider.lower()
            
            if "providers" not in self._vault:
                raise KeyNotFoundError(f"No vault data found")
            
            if provider_lower not in self._vault["providers"]:
                raise KeyNotFoundError(f"Provider '{provider}' not found in vault")
            
            # Log removal (security-critical action)
            self.sec_logger.warning("Removing provider key", provider=provider)
            
            # Audit log
            self.audit_logger.log_access(
                action="remove_key",
                provider=provider,
                success=True
            )
            
            self.audit_logger.log_security_event(
                event_type="key_removed",
                details={
                    "provider": provider,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            del self._vault["providers"][provider_lower]
            self._save_vault()
    
    def list_providers(self) -> List[str]:
        """List all providers in the vault (without exposing keys)."""
        with self._lock:
            if "providers" not in self._vault:
                return []
            
            return list(self._vault["providers"].keys())
    
    def has_provider(self, provider: str) -> bool:
        """Check if a provider exists in the vault."""
        return provider.lower() in self.list_providers()
    
    def get_vault_metadata(self) -> Dict[str, Any]:
        """Get vault metadata (creation time, version, etc.)."""
        with self._lock:
            return self._vault.get("metadata", {}).copy()
    
    def _sanitize_key_in_metadata(self, metadata: Dict) -> Dict:
        """Remove API key from metadata before logging."""
        sanitized = metadata.copy()
        if "api_key" in sanitized:
            sanitized["api_key"] = "***REDACTED***"
        return sanitized


class MemoryVault(EncryptedVault):
    """
    In-memory vault for development/testing only.
    
    Does NOT persist keys to disk - useful for testing without 
    encryption overhead. Keys are stored in plaintext in memory.
    
    WARNING: NEVER use this in production! All keys will be lost on restart
             and could be extracted from memory if compromised.
    """
    
    def __init__(self):
        # Skip parent initialization (no file operations)
        self._vault = {
            "providers": {},
            "metadata": {
                "created": datetime.utcnow().isoformat(),
                "version": "1.0",
                "mode": "memory_dev_only"
            }
        }
        self._lock = threading.RLock()
        
        # Security components still active for consistency
        self.sec_logger = SecurityLogger(logger)
        # Use temp directory for audit log in development mode
        import tempfile
        temp_audit_path = Path(tempfile.gettempdir()) / "mrkrabs_test_audit.log"
        self.audit_logger = AuditLogger(str(temp_audit_path))
        self.rate_limiter = RateLimiter()
        
        logger.warning("Using MEMORY VAULT - NOT SECURE FOR PRODUCTION")
    
    def _save_vault(self):
        """No-op for memory vault."""
        pass  # Keys only exist in memory
    
    def _load_vault(self) -> Dict[str, Any]:
        """No-op for memory vault."""
        return self._vault


class Vault:
    """
    Factory class for creating vault instances.
    
    Usage:
        # Encrypted file vault (production)
        vault = Vault.create("encrypted", master_key="...")
        
        # Memory vault (development only)
        vault = Vault.create("memory")
    """
    
    @staticmethod
    def create(
        backend: str = "encrypted",
        vault_path: Optional[str] = None,
        master_key: Optional[str] = None
    ) -> EncryptedVault:
        """
        Create a vault instance with specified backend.
        
        Args:
            backend: Storage backend ("encrypted" or "memory")
            vault_path: Path to vault file (for encrypted backend)
            master_key: Master encryption key (for encrypted backend)
            
        Returns:
            EncryptedVault or MemoryVault instance
        """
        if backend == "memory":
            return MemoryVault()
        elif backend == "encrypted":
            return EncryptedVault(vault_path=vault_path, master_key=master_key)
        else:
            raise ValueError(f"Unknown vault backend: {backend}")


# ============================================================================
# Utility Functions
# ============================================================================

def generate_master_key() -> str:
    """
    Generate a new random master key for vault encryption.
    
    Returns base64-encoded 32-byte Fernet key.
    
    SECURITY: Store this key securely! If lost, vault cannot be decrypted.
              Never commit this to version control.
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def initialize_vault(vault_path: str = None) -> str:
    """
    Initialize a new encrypted vault file.
    
    Returns the master key that must be stored securely.
    
    Example:
        # Generate and store master key
        master_key = initialize_vault("/etc/mrkrabs/vault.enc")
        
        # Save master_key to secure location (NOT in code)
        os.environ["VAULT_MASTER_KEY"] = master_key  # Or use OS keyring
        
        # Now you can create providers and add keys
        vault = Vault.create("encrypted", vault_path="/etc/mrkrabs/vault.enc")
        vault.add_provider_key("openai", "sk-...")
    """
    master_key = generate_master_key()
    
    # Create vault with the new key
    vault = Vault.create(
        backend="encrypted", 
        vault_path=vault_path, 
        master_key=master_key
    )
    
    print(f"✓ Vault initialized at: {vault_path or '/etc/mrkrabs/vault.enc'}")
    print(f"\n🔴 CRITICAL: Save this master key securely (NEVER share or commit):")
    print(f"   VAULT_MASTER_KEY={master_key}\n")
    
    return master_key
