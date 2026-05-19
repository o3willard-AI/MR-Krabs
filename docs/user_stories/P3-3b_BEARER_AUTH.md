# Story P3-3b: Bearer Token Authentication

**Priority:** P1 (High — production security requirement)
**Estimate:** 3 days
**Phase:** Phase 3 — Week 7

---

## User Story

As a **security engineer** deploying MR-Krabs,
I want Bearer token and API key authentication on the MCP server
So that only authorized clients can call MR-Krabs endpoints, meeting enterprise security standards.

---

## Acceptance Criteria

### AC1: Forked Auth Middleware
- [ ] Fork authentication patterns from `litellm/middleware/auth_utils.py` into `src/mcp/auth.py`
- [ ] Implement as FastAPI middleware (not adapter — auth is a cross-cutting concern):
  ```python
  # Applied to all routes except /health and /ready
  app.add_middleware(AuthenticationMiddleware)
  ```
- [ ] Support two authentication methods (configurable per-endpoint):
  - **Bearer Token**: `Authorization: Bearer <token>`
  - **API Key**: `X-API-Key: <key>`
- [ ] Both methods checked against vault-stored credentials

### AC2: Vault-Integrated Credential Store
- [ ] Authentication credentials stored in encrypted vault:
  ```
  /auth/tokens/<token_id>  → { "token": "<hash>", "roles": ["read", "admin"], "expires": "..." }
  /auth/api_keys/<key_id>  → { "key": "<hash>", "roles": ["read"], "expires": "..." }
  ```
- [ ] Passwords/tokens hashed with bcrypt before storage (never stored in plaintext)
- [ ] Token lookup: constant-time comparison to prevent timing attacks
- [ ] Expired credentials rejected with `401 Token expired`

### AC3: Role-Based Access Control
- [ ] Three roles defined:
  - **`read`**: Can call `ask()`, query analytics, read health
  - **`write`**: `read` + can create/manage tasks, update config
  - **`admin`**: `write` + can rotate keys, force circuit breaker state, view all tokens
- [ ] Role enforcement via FastAPI dependency:
  ```python
  @app.post("/ask")
  @requires_role("read")  # ← dependency injection
  async def ask_endpoint(...): ...
  
  @app.post("/admin/circuit/reset")
  @requires_role("admin")
  async def reset_circuit(...): ...
  ```
- [ ] Unauthorized role attempts return `403 Forbidden` with `X-Required-Role: admin` header

### AC4: Token Management
- [ ] Admin CLI for token lifecycle:
  ```bash
  mrkrabs auth create-token --role read --expires 30d --note "CI pipeline"
  mrkrabs auth list-tokens
  mrkrabs auth revoke <token_id>
  mrkrabs auth rotate <token_id>  # creates new token, revokes old after grace period
  ```
- [ ] MCP management tools: `manage_tokens()`, `create_api_key()`, `revoke_credential()`
- [ ] Token rotation: old token valid for configurable grace period (default: 1 hour)
- [ ] Audit log: every token creation, revocation, and usage logged with timestamp

### AC5: Authentication Configuration
- [ ] TOML config:
  ```toml
  [litellm.auth]
  enabled = false           # default OFF (backward compatible)
  methods = ["bearer"]      # "bearer", "api_key", or both
  token_expiry_default = "90d"
  require_auth_endpoints = ["/ask", "/admin/*", "/analytics/*"]
  public_endpoints = ["/health", "/ready", "/metrics"]
  rate_limit_per_token = 100  # requests per minute per token
  ```
- [ ] When `enabled = false`: all endpoints open (current behavior, backward compatible)
- [ ] When `enabled = true`: `public_endpoints` remain open, everything else requires auth

### AC6: Security Hardening
- [ ] Rate limiting per token: configurable requests/minute (default: 100)
- [ ] Brute force protection: 5 failed auth attempts → 60s lockout for that IP
- [ ] Token usage metrics: `mrkrabs_auth_requests_total{token_id, endpoint, status}`
- [ ] Failed auth alerts: >10 failures/minute triggers Prometheus alert
- [ ] Security headers on all responses: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`

---

## Technical Notes

- Use FastAPI's `Depends()` for clean role-based access — no monkey-patching
- bcrypt cost factor: 12 (balance of security vs. latency at auth check time)
- Token format: `mrkrabs_<32_bytes_base64url>` — prefixed for easy identification in logs
- Constant-time comparison: `hmac.compare_digest()` — never use `==` for token comparison
- Audit log: structured JSON to `~/.mrkrabs/logs/auth.log`, rotate daily

---

## Definition of Done

- [ ] `AuthenticationMiddleware` implemented and integrated with FastAPI app
- [ ] Vault-backed credential store with bcrypt hashing
- [ ] RBAC: read/write/admin roles enforced on all endpoints
- [ ] Token management CLI functional
- [ ] Brute force protection working
- [ ] All existing tests pass with `[litellm.auth].enabled = false`
- [ ] Auth-specific tests: token create/use/expire/revoke, role enforcement, rate limiting
- [ ] Tests: `pytest tests/integration_litellm/phase_3/test_auth.py -v`
