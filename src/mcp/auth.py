"""
Authentication module for MR-Krabs MCP Server.
Provides JWT-based authentication, API key management, and rate limiting.
"""

import hmac
import hashlib
import base64
import json
import time
import os
from typing import Dict, List, Optional
from collections import defaultdict, deque

# Simple HS256 JWT implementation using only Python stdlib
def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _b64_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)

def create_jwt(payload: dict, secret: str) -> str:
    """Create a JWT token with HS256 signature."""
    header = _b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_b64 = _b64_encode(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload_b64}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload_b64}.{_b64_encode(signature)}"

def verify_jwt(token: str, secret: str) -> dict:
    """Verify a JWT token and return its payload."""
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header_b64, payload_b64, sig_b64 = parts
    expected_sig = _b64_encode(hmac.new(secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64_decode(payload_b64))
    if payload.get('exp', 0) < time.time():
        raise ValueError("Token expired")
    return payload


class AuthManager:
    """JWT-based authentication manager."""
    
    def __init__(self, secret_key: str, token_expiry_minutes: int = 60):
        self.secret_key = secret_key
        self.token_expiry_minutes = token_expiry_minutes
    
    def create_token(self, client_id: str, scopes: List[str] = None) -> str:
        """Create a JWT token for a client."""
        payload = {
            "sub": client_id,
            "exp": int(time.time() + (self.token_expiry_minutes * 60)),
            "iat": int(time.time()),
        }
        if scopes:
            payload["scopes"] = scopes
        
        return create_jwt(payload, self.secret_key)
    
    def validate_token(self, token: str) -> dict:
        """Validate a JWT token and return its payload."""
        return verify_jwt(token, self.secret_key)
    
    def rotate_keys(self) -> None:
        """Rotate the signing key (not implemented in this basic version)."""
        # In a real implementation, this would generate a new key
        # and keep old keys valid for a grace period
        pass


class KeyManager:
    """API Key management for backward compatibility."""
    
    def __init__(self):
        self.keys: Dict[str, Dict] = {}  # key -> {label, created_at}
        self.key_order = []  # Maintain insertion order for list_keys
    
    def add_key(self, key: str, label: str) -> None:
        """Add a new API key."""
        if key not in self.keys:
            self.keys[key] = {
                "label": label,
                "created_at": time.time()
            }
            self.key_order.append(key)
    
    def validate_key(self, key: str) -> bool:
        """Validate an API key."""
        return key in self.keys
    
    def list_keys(self) -> List[Dict]:
        """List all API keys (masked for security)."""
        result = []
        for key, info in self.keys.items():
            # Mask the key (show first 4 and last 4 chars)
            masked_key = key[:4] + "*" * max(0, len(key) - 8) + key[-4:]
            result.append({
                "key": masked_key,
                "label": info["label"],
                "created_at": info["created_at"]
            })
        return result
    
    def revoke_key(self, key: str) -> None:
        """Revoke an API key."""
        if key in self.keys:
            del self.keys[key]
            self.key_order = [k for k in self.key_order if k != key]
    
    def rotate_keys(self) -> tuple[str, str]:
        """Generate a new key and return (old_key, new_key)."""
        # This is a placeholder - in real implementation this would create new keys
        raise NotImplementedError("Key rotation not implemented in this basic version")


class RateLimiter:
    """Simple sliding window rate limiter."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)  # client_id -> deque of timestamps
    
    def check(self, client_id: str) -> bool:
        """Check if a request is allowed for the client."""
        now = time.time()
        # Remove old requests outside the window
        while (self.requests[client_id] and 
               self.requests[client_id][0] <= now - self.window_seconds):
            self.requests[client_id].popleft()
        
        # Check if we've exceeded the limit
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[client_id].append(now)
        return True
    
    def get_remaining(self, client_id: str) -> int:
        """Get number of requests remaining in the window."""
        now = time.time()
        # Remove old requests outside the window
        while (self.requests[client_id] and 
               self.requests[client_id][0] <= now - self.window_seconds):
            self.requests[client_id].popleft()
        
        return max(0, self.max_requests - len(self.requests[client_id]))


# FastAPI Middleware
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication and rate limiting middleware."""
    
    PUBLIC_PATHS = {"/", "/health", "/tools", "/docs", "/openapi.json", "/redoc"}
    
    def __init__(self, app, auth_manager: AuthManager, key_manager: KeyManager, rate_limiter: RateLimiter):
        super().__init__(app)
        self.auth_manager = auth_manager
        self.key_manager = key_manager
        self.rate_limiter = rate_limiter
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PUBLIC_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)
        
        auth_header = request.headers.get("Authorization", "")
        
        # Try Bearer token (JWT or API key)
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Try JWT first, then API key
            try:
                payload = self.auth_manager.validate_token(token)
                request.state.client_id = payload.get("sub", "unknown")
            except Exception:
                if self.key_manager.validate_key(token):
                    request.state.client_id = "api-key"
                else:
                    raise HTTPException(status_code=401, detail="Invalid or expired token")
        else:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        # Rate limiting
        client_id = request.state.client_id
        if not self.rate_limiter.check(client_id):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(self.rate_limiter.get_remaining(client_id))
        return response