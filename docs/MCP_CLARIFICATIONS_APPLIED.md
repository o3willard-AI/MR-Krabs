# MR-Krabs MCP Server - Clarifications Applied

**Date**: May 5, 2026  
**Status**: All design decisions finalized and applied to implementation plan

---

## Summary of User Clarifications

The following clarifications were provided and applied to the MCP_SERVER_IMPLEMENTATION_PLAN.md:

### 1. Budget Enforcement - Configurable Modes ✅

**Decision**: Support four enforcement modes

- **`notify_only`**: Warn when budget threshold reached, but continue execution
- **`fail`**: Immediately fail when budget would be exceeded
- **`notify_then_fail`**: Warn at threshold (80%), then fail at 100% - **DEFAULT**
- **`fail_with_notification`**: Fail and provide detailed notification about budget

**Implementation**: 
- Configurable per-session or globally via config file
- Default: `notify_then_fail` at 80% warning, hard fail at 100%
- Implemented in P0-S3 and P1-S2

### 2. Session Management - Stateful with Stateless Option ✅

**Decision**: Primary mode is stateful (maintains state across tool calls)

**Stateful Mode** (Recommended):
```python
# Create session once
session_id = mcp_mrkrabs_init_session(budget=10.0, enforcement_mode="notify_then_fail")

# Reuse session_id in subsequent calls
mcp_mrkrabs_cost_estimate(session_id=session_id, prompt_tokens=100)
mcp_mrkrabs_crew_execute(session_id=session_id, crew_config=...)
```

**Stateless Mode** (Fallback):
```python
# Full config in each call - no session management needed
mcp_mrkrabs_cost_estimate(
    config={"budget": 10.0, "enforcement_mode": "fail"},
    prompt_tokens=100
)
```

**Implementation**:
- Session store with TTL (default 1 hour)
- Unique session_id per session
- Configurable via `SESSION_TTL` environment variable
- Implemented in P0-S2 and P0-S3

### 3. Production-Ready Documentation - Phase 3 ✅

**Decision**: Comprehensive docs created in Phase 3 (not deferred to Phase 4)

**Deliverables**:
- `/docs/MCP_SERVER.md` - Main architecture and usage guide
- `/docs/MCP_TOOLS_REFERENCE.md` - Complete tool schema reference
- `/examples/mcp_quickstart.py` - Minimal working example
- `/examples/mcp_integration.py` - Full integration example
- README updates with MCP section

**New Story**: P3-S4 added specifically for documentation creation (5-6 hours)

### 4. Transport - HTTP (Local + Remote) ✅

**Decision**: HTTP transport supporting both local and remote access

**Implementation**:
- FastAPI-based server (or httpx)
- Default: `localhost:8000`
- Configurable via environment variables:
  - `MCP_HOST=0.0.0.0` (default)
  - `MCP_PORT=8000` (default)

**Benefits**:
- Local development: `curl http://localhost:8000/...`
- Remote access: Bind to specific interface, firewall rules
- Easy health checks and monitoring
- Standard HTTP tooling and debugging

**Updated Stories**:
- P0-S1: Updated to specify HTTP transport implementation
- P0-S2: Rewrote server skeleton to use FastAPI instead of stdio

### 5. Authentication - Optional Initially ✅

**Decision**: Auth not required for Phase 1-3, optional via environment variable

**Implementation**:
- Environment variable `MCP_API_KEY` (optional)
- If set, requires `Authorization: Bearer <key>` header
- If not set, no authentication required
- Full auth middleware added in Phase 4

**Rationale**:
- Enable quick development and local testing
- No barrier to entry for initial users
- Can be secured later when deploying to production

### 6. Deployment - Native Python First ✅

**Decision**: Start with native Python script deployment, Docker in Phase 5

**Phase 1-4 Deployment**:
```bash
# Simple run
python -m src.mcp.server

# With custom config
MCP_PORT=9000 SESSION_TTL=7200 python -m src.mcp.server

# As systemd service (optional)
systemctl start mrkrabs-mcp-server
```

**Phase 5+ Deployment** (Future):
- Dockerfile and docker-compose.yml
- Kubernetes manifests
- Container orchestration

**Updated Stories**:
- P4-S3: Changed to "Native Python" deployment scripts only
- P5-S1: New story for Docker support in future phase

### 7. Tool Naming - `mcp_mrkrabs_*` Prefix Confirmed ✅

**Decision**: All tools prefixed with `mcp_mrkrabs_`

**Tool Categories**:
```
mcp_mrkrabs_session_*    # Session lifecycle management
  - init_session
  - close_session
  - get_session_status

mcp_mrkrabs_cost_*       # Cost estimation and tracking
  - estimate_cost
  - track_spending
  - get_cost_breakdown

mcp_mrkrabs_budget_*     # Budget management
  - check_remaining
  - set_enforcement_mode
  - get_budget_status

mcp_mrkrabs_crew_*       # CrewAI orchestration
  - create_crew
  - execute_crew
  - get_crew_result

mcp_mrkrabs_agent_*      # Single agent execution
  - execute_task
  - execute_with_escalation

mcp_mrkrabs_analytics_*  # Reporting and metrics
  - get_daily_report
  - export_costs
  - get_efficiency_metrics
```

---

## Updated Implementation Plan Structure

### Phase 0: Foundation & Design (Week 1)
- P0-S1: Define MCP Server Architecture (updated with HTTP, sessions, enforcement modes)
- P0-S2: Implement Basic MCP Server Skeleton (rewritten for FastAPI/HTTP)
- P0-S3: Define Configuration & State Management Strategy (expanded with enforcement modes)

### Phase 1: Core Cost Tools + Session Mgmt (Weeks 2-3)
- P1-S1: Estimate cost before execution
- P1-S2: Check remaining budget (with enforcement mode support)
- P1-S3: Track actual spending (with configurable enforcement)

### Phase 2: CrewAI Orchestration (Weeks 4-5)
- P2-S1: Create and execute multi-agent crew (stateful)
- P2-S2: Execute crew and retrieve results
- P2-S3: Execute single agent task (supports both modes)

### Phase 3: Analytics & Production Docs (Weeks 6-7)
- P3-S1: Get daily cost report
- P3-S2: Export cost data (CSV/JSON)
- P3-S3: Get efficiency metrics
- **P3-S4**: Create Production-Ready Documentation **(NEW)**

### Phase 4: Auth & CI/CD (Week 8)
- P4-S1: Add Authentication & Authorization (optional auth)
- P4-S2: Finalize Documentation & Create Examples
- P4-S3: Create Deployment Scripts (Native Python)
- P4-S4: Integration tests with real MCP client

### Phase 5: Future Enhancements
- **P5-S1**: Docker Support **(MOVED from P4)**
- Multi-tenant support
- Advanced features

---

## Key Files to Review

After applying clarifications, review these sections in MCP_SERVER_IMPLEMENTATION_PLAN.md:

1. **Top section**: New "Design Decisions - CONFIRMED" summary table
2. **P0-S1**: Updated tool structure with session management
3. **P0-S2**: Complete FastAPI server skeleton code
4. **P0-S3**: Budget enforcement modes and session lifecycle
5. **P3-S4**: New documentation story (production-ready docs)
6. **P4-S3**: Changed to native Python deployment only
7. **P5-S1**: New Docker story for future phase

---

## Next Steps

1. ✅ Review updated MCP_SERVER_IMPLEMENTATION_PLAN.md
2. ✅ Confirm all clarifications are correctly applied
3. 🔄 Begin Phase 0 implementation (if approved)
4. 🔄 Or request further refinements to specific stories

---

**Document**: `/home/sblanken/working/code/MR-Krabs/docs/MCP_SERVER_IMPLEMENTATION_PLAN.md`  
**Changes Applied**: All 7 clarifications integrated into implementation plan  
**Status**: Ready for review and Phase 0 kickoff
