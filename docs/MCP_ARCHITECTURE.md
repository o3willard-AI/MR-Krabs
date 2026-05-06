# MR-Krabs MCP Server Architecture

**Version**: 0.2.0-dev  
**Date**: May 5, 2026  
**Status**: Phase 1 Complete (Cost Management Tools)

---

## Overview

The MR-Krabs MCP Server exposes the cost-optimized AI orchestration capabilities of MR-Krabs as reusable tools via the Model Context Protocol (MCP). This allows higher-level AI agents to leverage multi-agent workflows with automatic cost tracking and budget enforcement without understanding MR-Krabs internals.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Higher-Level Agent                       │
│                 (Cursor, Claude Code, etc.)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/JSON
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   MCP Server Layer                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              FastAPI Application                       │  │
│  │  - Authentication (optional API key)                   │  │
│  │  - Request validation                                  │  │
│  │  - Tool routing                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Session Manager                           │  │
│  │  - Stateful sessions with TTL                          │  │
│  │  - Thread-safe concurrent access                       │  │
│  │  - Stateless fallback support                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Budget Enforcer                           │  │
│  │  - 4 enforcement modes                                 │  │
│  │  - Real-time budget tracking                           │  │
│  │  - Configurable thresholds                             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  MR-Krabs Core Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Cost Tracker │  │ Tier Manager │  │ CrewAI       │      │
│  │              │  │              │  │ Integration  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Providers    │  │ Metrics      │  │ Reports      │      │
│  │ (OpenRouter, │  │ Collection   │  │ & Analytics  │      │
│  │ LM Studio)   │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### Transport: HTTP (FastAPI)

**Decision**: Use FastAPI over stdio transport

**Rationale**:
- Supports both local development and remote deployment
- Standard HTTP tooling for debugging and monitoring
- Easy health checks and service discovery
- Compatible with container orchestration (Kubernetes, etc.)

**Configuration**:
```bash
MCP_HOST=0.0.0.0       # Bind address
MCP_PORT=8000          # Port number
SESSION_TTL=3600       # Session TTL in seconds
MCP_API_KEY=optional   # API key for auth (if set)
```

### Session Management: Stateful + Stateless

**Primary Mode**: Stateful sessions with unique session_id

```python
# Create session once
session_id = mcp_mrkrabs_session_init(
    budget_limit=10.0,
    enforcement_mode="notify_then_fail"
)

# Reuse in subsequent calls
mcp_mrkrabs_cost_estimate(session_id=session_id, ...)
mcp_mrkrabs_crew_execute(session_id=session_id, ...)
```

**Fallback Mode**: Stateless with full config per call

```python
# No session needed
mcp_mrkrabs_cost_estimate(
    config={"budget_limit": 10.0},
    prompt_tokens=100
)
```

**Benefits**:
- Stateful: Natural workflow, no config repetition
- Stateless: Simple one-off operations, stateless scaling

### Budget Enforcement: Configurable Modes

Four enforcement strategies for different use cases:

| Mode | Warning | On Exceed | Use Case |
|------|---------|-----------|----------|
| `notify_only` | At 80% | Continue | Monitoring without blocking |
| `fail` | None | Block immediately | Strict budget control |
| `notify_then_fail` | At 80% | Block at 100% | Default, balanced approach |
| `fail_with_notification` | None | Block with details | User-friendly errors |

### Authentication: Optional Initially

**Phase 1-3**: No authentication required

**Rationale**:
- Lower barrier to entry for development
- Enable quick local testing
- No friction for internal tools

**Phase 4+**: Optional API key via environment variable

```bash
MCP_API_KEY=your-secret-key

# Client must send:
Authorization: Bearer your-secret-key
```

---

## Component Details

### Session Manager

**Location**: `src/mcp/session_manager.py`

**Responsibilities**:
- Create, retrieve, delete sessions
- TTL-based automatic expiration
- Thread-safe concurrent access
- Configuration storage per session

**Data Structure**:
```python
class SessionConfig:
    session_id: str
    budget_limit: float          # Default: 10.0
    enforcement_mode: str        # Default: notify_then_fail
    warning_threshold: float     # Default: 80.0
    default_tier: str           # Default: "L0"
    models: List[str]           # Allowed LLM models
    created_at: float           # Unix timestamp
    last_accessed: float        # Unix timestamp
    ttl_seconds: int            # Default: 3600
```

**Thread Safety**: Uses `threading.RLock()` for all operations

### Budget Enforcer

**Location**: `src/mcp/budget_enforcer.py`

**Responsibilities**:
- Track spending per session
- Check if operations can proceed
- Enforce budget limits based on mode
- Provide detailed status reports

**Key Methods**:
```python
check_budget(would_spend: float) -> BudgetCheckResult
record_spending(amount: float) -> None
get_status() -> dict
```

### MCP Server (FastAPI)

**Location**: `src/mcp/server.py`

**Endpoints**:

#### Health & Status
- `GET /health` - Health check for load balancers
- `GET /` - Service information
- `GET /tools` - List all available tools

#### Session Management
- `POST /tools/mcp_mrkrabs_session_init` - Create new session
- `GET /tools/mcp_mrkrabs_session_status/{id}` - Check session status
- `DELETE /tools/mcp_mrkrabs_session_close/{id}` - Close session

#### Tools (All support optional `session_id`)
- `POST /tools/mcp_mrkrabs_ping` - Connectivity test
- `POST /tools/mcp_mrkrabs_cost_estimate` - Estimate LLM costs
- `POST /tools/mcp_mrkrabs_budget_check` - Check remaining budget
- ... (additional tools in later phases)

---

## Data Flow

### Stateful Request Flow

```
1. Client → POST /tools/mcp_mrkrabs_session_init
   Body: {budget_limit: 10.0, enforcement_mode: "notify_then_fail"}
   
2. Server → Create SessionConfig, store in SessionManager
   Returns: {session_id: "session-a1b2c3d4", ...}

3. Client → POST /tools/mcp_mrkrabs_cost_estimate
   Body: {session_id: "session-a1b2c3d4", prompt_tokens: 100, ...}
   
4. Server → Retrieve SessionConfig from session_id
          Apply budget enforcement
          Execute cost estimation
          
5. Server → Returns: {estimated_cost: 0.05, warning: ..., ...}
```

### Stateless Request Flow

```
1. Client → POST /tools/mcp_mrkrabs_cost_estimate
   Body: {config: {budget_limit: 10.0}, prompt_tokens: 100, ...}
   
2. Server → Create temporary SessionConfig from config param
          Apply budget enforcement (no storage)
          Execute cost estimation
          
3. Server → Returns: {estimated_cost: 0.05, ...}
```

---

## Security Considerations

### Current Phase (0-3)
- No authentication required
- Suitable for local/development use
- Not recommended for production without auth

### Production Hardening (Phase 4+)
- API key authentication via `MCP_API_KEY` env var
- HTTPS/TLS termination (handled by reverse proxy)
- Rate limiting (to be added)
- Request logging and audit trail

---

## Performance Characteristics

### Session Storage
- **Backend**: In-memory dictionary
- **Max Sessions**: Limited by available RAM
- **Concurrent Access**: Thread-safe with RLock
- **Future**: Redis/DB backend for distributed deployments (Phase 5)

### Request Latency
- **Health check**: <10ms
- **Session operations**: <50ms
- **Cost estimation**: <100ms
- **Crew execution**: Variable (depends on task complexity)

### Scaling
- **Horizontal**: Each instance has independent session store
- **Vertical**: Limited by memory for session storage
- **Recommendation**: Use sticky sessions or shared session backend for scale

---

## Error Handling

### HTTP Status Codes
- `200` - Success
- `401` - Authentication required/failed
- `403` - Invalid API key
- `404` - Session not found / Tool not implemented
- `409` - Budget exceeded (enforcement mode: fail)
- `500` - Internal server error

### Error Response Format
```json
{
    "detail": "Budget exceeded: would spend $15.00 of $10.00"
}
```

---

## Future Enhancements

### Phase 4+
- [ ] Full authentication middleware
- [ ] Rate limiting per session/IP
- [ ] Request logging and metrics
- [ ] Circuit breaker for downstream services

### Phase 5+
- [ ] Redis/DB backend for sessions (distributed)
- [ ] Multi-tenant support
- [ ] WebSocket support for real-time updates
- [ ] gRPC transport option

---

## Testing Strategy

### Unit Tests
- Session manager operations (create, get, delete, expire)
- Budget enforcer modes and calculations
- Request validation and error handling

### Integration Tests
- End-to-end tool execution flows
- Session lifecycle management
- Concurrent session access

### Performance Tests
- Session creation/deletion at scale
- Concurrent request handling
- Memory usage under load

---

## Deployment Options

### Local Development
```bash
cd /home/sblanken/working/code/MR-Krabs
python -m src.mcp.server
```

### Production (Native Python)
```bash
MCP_HOST=0.0.0.0 MCP_PORT=8000 python -m src.mcp.server
```

### Production (Systemd)
```ini
# /etc/systemd/system/mrkrabs-mcp-server.service
[Service]
ExecStart=/usr/bin/python3 -m src.mcp.server
Environment=MCP_HOST=0.0.0.0
Environment=MCP_PORT=8000
Restart=always
```

### Production (Docker) - Phase 5
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install .
CMD ["python", "-m", "src.mcp.server"]
```

---

## References

- [MCP Server Implementation Plan](./MCP_SERVER_IMPLEMENTATION_PLAN.md)
- [Tool Reference Documentation](./MCP_TOOLS_REFERENCE.md) (Phase 3)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
