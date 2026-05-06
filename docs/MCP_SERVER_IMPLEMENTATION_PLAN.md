# MR-Krabs MCP Server Implementation Plan

**Date**: May 5, 2026  
**Last Updated**: May 5, 2026 (clarifications applied)  
**Objective**: Transform MR-Krabs into a reusable subagent capability via Model Context Protocol (MCP)  
**Vision**: Higher-level agents can orchestrate multi-agent workflows with cost optimization without understanding MR-Krabs internals

---

## ✅ Design Decisions - CONFIRMED

All design decisions have been finalized based on user clarifications:

| Decision | Value | Rationale |
|----------|-------|-----------|
| **Transport** | HTTP (localhost:8000) | Supports both local and remote access |
| **Session Management** | Stateful with stateless fallback | Natural workflow + simple operations support |
| **Budget Enforcement** | 4 configurable modes | Flexibility for different use cases |
| **Authentication** | Optional initially | Enable quick development, add in Phase 4 |
| **Deployment** | Native Python first | Lower barrier to entry, easier debugging |
| **Tool Naming** | `mcp_mrkrabs_*` prefix | Clear namespace separation |
| **Documentation** | Production-ready in Phase 3 | Users need docs early for integration |
| **Docker** | Phase 5 (Future) | Not required for initial deployment |

### Budget Enforcement Modes

Four enforcement modes to handle budget limits:

1. **`notify_only`**: Warn when threshold reached, continue execution
2. **`fail`**: Immediately fail when budget would be exceeded
3. **`notify_then_fail`**: Warn at 80%, fail at 100% (DEFAULT)
4. **`fail_with_notification`**: Fail with detailed error message

### Session Management

**Primary Mode - Stateful:**
```bash
# Create session
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '{"budget": 10.0, "enforcement_mode": "notify_then_fail"}'

# Returns: {"session_id": "session-a1b2c3d4", ...}

# Use session in subsequent calls
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-a1b2c3d4", "prompt_tokens": 100, ...}'
```

**Fallback Mode - Stateless:**
```bash
# Full config in each call (no session required)
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d '{"config": {"budget": 10.0}, "prompt_tokens": 100, ...}'
```

---

## 🎯 Executive Summary

### Problem Statement
MR-Krabs currently operates as a standalone orchestrator. While powerful, it requires users to:
1. Learn the MR-Krabs API and architecture
2. Import and configure the library in their codebase  
3. Understand tier management, cost tracking, and budget enforcement concepts

This creates friction for adoption as a **reusable capability** within higher-level AI agents (like you!).

### Solution: MCP Server
By exposing MR-Krabs as an MCP server, we enable:
- ✅ **Zero-code integration**: Higher-level agents use tools natively
- ✅ **Configuration-as-data**: All settings passed as tool parameters
- ✅ **Subagent pattern**: MR-Krabs becomes a specialized capability provider
- ✅ **Dynamic orchestration**: Agents can create crews/workflows on-the-fly based on user intent

### End Goal
```python
# Instead of this (current approach):
from mrkrabs import CostAwareCrew, CostAwareAgent
crew = CostAwareCrew(...)

# Higher-level agents do this:
mcp_mrkrabs_create_crew(
    agents=[...], tasks=[...], budget=10.00
)
```

---

## 📊 Phase Breakdown Overview

| Phase | Timeline | Focus | Deliverable |
|-------|----------|-------|-------------|
| **Phase 0** | Week 1 | Foundation & Design | MCP server spec, HTTP transport, session management |
| **Phase 1** | Weeks 2-3 | Core Cost Tools + Session Mgmt | Cost tracking, budget enforcement modes, session lifecycle |
| **Phase 2** | Weeks 4-5 | CrewAI Orchestration | Full CrewAI integration via MCP tools (stateful) |
| **Phase 3** | Weeks 6-7 | Analytics & Production Docs | Reporting tools, comprehensive documentation |
| **Phase 4** | Week 8 | Auth & CI/CD | Optional auth, deployment scripts, integration tests |
| **Phase 5** | Future | Docker & Advanced Features | Containerization, multi-tenant support |

---

## 🏗️ Phase 0: Foundation & Design (Week 1)

### Objective
Design the MCP server architecture, define tool schemas, and set up development environment.

### User Stories

#### P0-S1: Define MCP Server Architecture
**As a** system architect  
**I want to** design a clean MCP server that exposes MR-Krabs capabilities as discrete tools  
**So that** higher-level agents can compose workflows without understanding internal complexity

**Acceptance Criteria:**
- [ ] Document MCP server architecture in `/docs/MCP_ARCHITECTURE.md`
- [ ] Define tool categories (Cost, CrewAI, Analytics, Config, Session)
- [ ] Design HTTP transport implementation (FastAPI or httpx-based)
- [ ] Implement session management strategy (stateful with stateless fallback)
- [ ] Plan budget enforcement modes (notify_only, fail, notify_then_fail, fail_with_notification)
- [ ] Specify error handling and validation patterns

**Technical Notes:**
```yaml
# Confirmed architecture decisions:
Transport: HTTP (localhost:8000 default, configurable)
State Management: Session-based with optional stateless mode
Budget Enforcement: 4 modes, default notify_then_fail at 80%
Auth: Optional initially (env var MCP_API_KEY)
Deployment: Native Python script first

# Proposed tool structure:
mcp_mrkrabs_ prefixed tools:
  ├─ mcp_mrkrabs_session_* (session lifecycle)
  │   ├─ init_session (create new session with config)
  │   ├─ close_session (cleanup session)
  │   └─ get_session_status (check active session)
  │
  ├─ mcp_mrkrabs_cost_* (cost tracking & budget)
  │   ├─ estimate_cost (estimate cost for tokens/model)
  │   ├─ track_spending (record actual spend)
  │   └─ get_cost_breakdown (detailed cost analysis)
  │
  ├─ mcp_mrkrabs_budget_* (budget management)
  │   ├─ check_remaining (get remaining budget)
  │   ├─ set_enforcement_mode (configure enforcement: notify_only, fail, etc.)
  │   └─ get_budget_status (comprehensive budget report)
  │
  ├─ mcp_mrkrabs_crew_* (orchestration - CrewAI)
  │   ├─ create_crew (define multi-agent workflow)
  │   ├─ execute_crew (run crew workflow)
  │   └─ get_crew_result (retrieve execution output)
  │
  ├─ mcp_mrkrabs_agent_* (single agent execution)
  │   ├─ execute_task (run single agent task)
  │   └─ execute_with_escalation (auto-escalate on failure)
  │
  └─ mcp_mrkrabs_analytics_* (reporting)
      ├─ get_daily_report (today's cost/usage summary)
      ├─ export_costs (CSV/JSON export)
      └─ get_efficiency_metrics (success rates, escalation stats)
```

**Deliverables:**
- Architecture document with diagrams
- HTTP server skeleton with FastAPI/httpx
- Session management implementation
- Tool schema JSON definitions
- Development environment setup script

**Estimate**: 6-8 hours

---

#### P0-S2: Implement Basic MCP Server Skeleton
**As a** developer  
**I want to** create a minimal working MCP server with HTTP transport that connects to MR-Krabs core  
**So that** I can iterate on tool implementations incrementally

**Acceptance Criteria:**
- [ ] MCP server project structure created at `src/mcp/`
- [ ] Server can start and respond to HTTP requests (health check, tool list)
- [ ] At least one "ping" tool working for connectivity test
- [ ] Session management skeleton implemented (create, read, delete sessions)
- [ ] Logging configured for debugging tool calls
- [ ] Unit tests scaffolded for MCP server
- [ ] Configurable host/port via environment variables

**Technical Implementation:**
```python
# src/mcp/server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid
import time

app = FastAPI(title="MR-Krabs MCP Server", version="0.1.0")

class SessionStore:
    """In-memory session storage with TTL"""
    def __init__(self, ttl_seconds=3600):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
    
    def create_session(self, config: Dict[str, Any]) -> str:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        self.sessions[session_id] = {
            "config": config,
            "created_at": time.time(),
            "last_accessed": time.time(),
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        # Check TTL
        if time.time() - session["last_accessed"] > self.ttl:
            del self.sessions[session_id]
            return None
        session["last_accessed"] = time.time()
        return session
    
    def delete_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

session_store = SessionStore(ttl_seconds=int(float(os.getenv("SESSION_TTL", "3600"))))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mr-krabs-mcp"}

@app.get("/tools")
async def list_tools():
    """List all available MCP tools"""
    return {
        "tools": [
            "mcp_mrkrabs_session_init",
            "mcp_mrkrabs_session_close",
            "mcp_mrkrabs_cost_estimate",
            "mcp_mrkrabs_budget_check",
            # ... additional tools
        ]
    }

@app.post("/tools/mcp_mrkrabs_session_init")
async def init_session(config: Dict[str, Any] = {}):
    """Initialize a new session with optional config"""
    session_id = session_store.create_session(config)
    return {
        "session_id": session_id,
        "status": "active",
        "config": config,
        "message": f"Session created. TTL: {session_store.ttl} seconds"
    }

@app.post("/tools/mcp_mrkrabs_ping")
async def ping(session_id: Optional[str] = None):
    """Test MCP connectivity"""
    if session_id:
        session = session_store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    return {
        "status": "ok",
        "message": "MR-Krabs MCP server is running!",
        "session_active": session_id is not None
    }

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
```

**Environment Variables:**
```bash
MCP_HOST=0.0.0.0          # Default: 0.0.0.0
MCP_PORT=8000             # Default: 8000
SESSION_TTL=3600          # Default: 1 hour in seconds
MCP_API_KEY=optional      # If set, requires Authorization header
```

**Running the Server:**
```bash
# Development
python -m src.mcp.server

# With custom config
MCP_PORT=9000 SESSION_TTL=7200 python -m src.mcp.server

# Test connectivity
curl http://localhost:8000/health
curl http://localhost:8000/tools
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_ping
```

**Deliverables:**
- Working HTTP MCP server skeleton
- Session management implementation
- Development run script (`python -m src.mcp.server`)
- Basic test suite structure
- Environment variable documentation

**Estimate**: 5-6 hours

---

#### P0-S3: Define Configuration & State Management Strategy
**As a** higher-level agent using MR-Krabs MCP tools  
**I want to** maintain configuration state across multiple tool calls without passing config every time  
**So that** I can set up once and execute workflows naturally

**Acceptance Criteria:**
- [ ] Implement session-based state management (per conversation/session) - PRIMARY MODE
- [ ] Support fully stateless mode as fallback for simple operations
- [ ] Implement config loading from `~/.cost_orchestrator.toml` on startup
- [ ] Allow runtime config overrides via tools
- [ ] Define session lifecycle (create, use, destroy, auto-expire)
- [ ] Handle concurrent sessions from multiple agents
- [ ] Implement budget enforcement modes per session

**Technical Design:**
```python
# Session management implementation

# Option A: Stateful (PRIMARY - recommended)
response = requests.post("http://localhost:8000/tools/mcp_mrkrabs_session_init", json={
    "budget": 10.00,
    "default_tier": "L0",
    "enforcement_mode": "notify_then_fail",
    "models": ["google/gemma-7b-it", ...]
})
session_id = response.json()["session_id"]  # e.g., "session-a1b2c3d4"

# Subsequent calls use session_id
requests.post(f"http://localhost:8000/tools/mcp_mrkrabs_cost_estimate", json={
    "session_id": session_id,
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "model": "google/gemma-7b-it"
})

# Stateless fallback (no session required)
requests.post("http://localhost:8000/tools/mcp_mrkrabs_cost_estimate", json={
    "config": {"budget": 10.00, "default_tier": "L0"},
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "model": "google/gemma-7b-it"
})

# Budget enforcement modes:
ENFORCEMENT_MODES = {
    "notify_only": {
        "description": "Warn when budget threshold reached, but continue execution",
        "threshold_warning": 80,  # Warn at 80%
        "on_exceed": "continue"
    },
    "fail": {
        "description": "Immediately fail when budget would be exceeded",
        "on_exceed": "raise_error"
    },
    "notify_then_fail": {
        "description": "Warn at threshold (80%), then fail at 100%",
        "threshold_warning": 80,
        "on_exceed": "raise_error"
    },
    "fail_with_notification": {
        "description": "Fail and provide detailed notification about budget",
        "on_exceed": "raise_error_with_details"
    }
}

# Session configuration structure:
class SessionConfig(BaseModel):
    session_id: str
    budget_limit: Optional[float] = 10.0  # Default $10/day
    enforcement_mode: str = "notify_then_fail"
    warning_threshold: float = 80.0  # Percent
    default_tier: str = "L0"
    models: List[str] = ["google/gemma-7b-it"]
    created_at: datetime
    last_accessed: datetime
    ttl_seconds: int = 3600
```

**Session Lifecycle:**
1. **Create**: `mcp_mrkrabs_session_init()` → returns session_id
2. **Use**: Include session_id in subsequent tool calls (optional for stateless)
3. **Auto-expire**: Sessions expire after TTL (default 1 hour of inactivity)
4. **Destroy**: `mcp_mrkrabs_session_close(session_id)` or let expire

**Concurrent Session Handling:**
- Each session isolated with unique session_id
- In-memory storage with thread-safe dict operations
- Future: Redis/DB backend for distributed deployments (Phase 5)

**Deliverables:**
- Session management implementation in `src/mcp/session_manager.py`
- Budget enforcement mode implementation in `src/mcp/budget_enforcer.py`
- Config loading from TOML file
- Documentation of session lifecycle and patterns

**Estimate**: 4-5 hours

---

### Phase 0 Success Criteria ✅
- [ ] Architecture document approved and documented
- [ ] MCP server skeleton runs without errors
- [ ] Tool schema definitions for all planned tools
- [ ] Development environment reproducible via `./scripts/setup_mcp_dev.sh`
- [ ] Basic tests passing (>80% coverage on MCP module)

---

## 💰 Phase 1: Core Cost Tools (Weeks 2-3)

### Objective
Implement cost tracking and budget management tools - the foundation of MR-Krabs value proposition.

### User Stories

#### P1-S1: Estimate Cost Before Execution
**As a** higher-level agent planning a workflow  
**I want to** estimate costs before committing to execution  
**So that** I can make informed decisions about budget allocation

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_cost_estimate` accepts tokens + model parameters
- [ ] Returns estimated cost in USD with breakdown (input/output tokens)
- [ ] Supports multiple models for comparison
- [ ] Handles unknown models gracefully (uses default pricing or returns error)
- [ ] Includes confidence interval or disclaimer if using estimates

**Tool Schema:**
```python
from pydantic import BaseModel, Field

class CostEstimateRequest(BaseModel):
    prompt_tokens: int = Field(..., description="Estimated input tokens")
    completion_tokens: int = Field(..., description="Estimated output tokens")
    model: str = Field(default="google/gemma-7b-it", description="LLM model name")
    
class CostEstimateResponse(BaseModel):
    estimated_cost_usd: float
    breakdown: dict  # {"prompt": 0.01, "completion": 0.02}
    model_pricing: dict  # Per-token rates used
    confidence: str = "estimate"  # Or "actual" if from recent execution

@mcp_mrkrabs.tool()
async def cost_estimate(ctx, request: CostEstimateRequest) -> CostEstimateResponse:
    """Estimate cost for LLM usage before execution"""
    tracker = CostTracker()
    cost = tracker.calculate_cost(request.model, TokenCount(
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
    ))
    return CostEstimateResponse(
        estimated_cost_usd=float(cost),
        breakdown={"prompt": ..., "completion": ...},
        model_pricing=tracker.get_model_pricing(request.model),
    )
```

**Deliverables:**
- Working cost estimation tool
- Integration with MR-Krabs CostTracker
- Test cases covering common models (gemma, llama, claude, gpt)

**Estimate**: 4-5 hours

---

#### P1-S2: Check Remaining Budget
**As a** higher-level agent managing costs  
**I want to** check how much budget remains before executing expensive operations  
**So that** I can avoid exceeding limits mid-workflow

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_budget_check` returns remaining budget for scope
- [ ] Supports multiple scopes: daily, weekly, project-based
- [ ] Shows current spend and limit
- [ ] Returns warning if close to limit (>80%)
- [ ] Handles missing config gracefully (returns unlimited or defaults)

**Tool Schema:**
```python
class BudgetCheckRequest(BaseModel):
    scope: str = Field(
        default="daily",
        description="Budget scope: daily, weekly, monthly, or project_id"
    )
    
class BudgetCheckResponse(BaseModel):
    limit_usd: float | None  # None = unlimited
    spent_usd: float
    remaining_usd: float
    percentage_used: float
    warning: str | None  # "Warning: 85% of budget used"

@mcp_mrkrabs.tool()
async def budget_check(ctx, request: BudgetCheckRequest) -> BudgetCheckResponse:
    """Check remaining budget for given scope"""
    tracker = CostTracker()
    stats = tracker.get_budget_stats(scope=request.scope)
    return BudgetCheckResponse(
        limit_usd=float(stats.limit) if stats.limit else None,
        spent_usd=float(stats.spent),
        remaining_usd=float((stats.limit or float('inf')) - stats.spent),
        percentage_used=(stats.spent / stats.limit * 100) if stats.limit else 0,
        warning=f"Warning: {stats.spent/stats.limit*100:.0f}% budget used" if stats.limit and stats.spent/stats.limit > 0.8 else None,
    )
```

**Deliverables:**
- Budget checking tool with scope support
- Integration with CostTracker budget tracking
- Test cases for various budget scenarios

**Estimate**: 3-4 hours

---

#### P1-S3: Track Actual Spending
**As a** higher-level agent that executed operations  
**I want to** record actual costs incurred during execution  
**So that** MR-Krabs can track real spending vs estimates

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_cost_record` accepts execution details
- [ ] Records cost in CostTracker with task categorization
- [ ] Updates budget tracking automatically
- [ ] Returns confirmation and updated remaining budget
- [ ] Handles errors (budget exceeded) with clear error messages

**Tool Schema:**
```python
class CostRecordRequest(BaseModel):
    task_id: str = Field(..., description="Unique identifier for this task")
    prompt_tokens: int = Field(..., description="Actual input tokens used")
    completion_tokens: int = Field(..., description="Actual output tokens used")
    model: str = Field(..., description="Model that was used")
    category: str = Field(default="orchestration", description="Task category for analytics")

class CostRecordResponse(BaseModel):
    recorded_cost_usd: float
    task_id: str
    remaining_budget_usd: float
    warning: str | None

@mcp_mrkrabs.tool()
async def cost_record(ctx, request: CostRecordRequest) -> CostRecordResponse:
    """Record actual cost from execution"""
    tracker = CostTracker()
    
    # Calculate actual cost
    tokens = TokenCount(
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
    )
    cost = tracker.calculate_cost(request.model, tokens)
    
    # Check budget before recording
    stats = tracker.get_budget_stats(scope="daily")
    if stats.limit and (stats.spent + cost) > stats.limit:
        raise ValueError(f"Budget exceeded: would spend ${stats.spent+cost:.2f} of ${stats.limit:.2f}")
    
    # Record the spending
    tracker.record_task(
        task_id=request.task_id,
        model=request.model,
        tokens=tokens,
        cost=cost,
        category=request.category,
    )
    
    return CostRecordResponse(
        recorded_cost_usd=float(cost),
        task_id=request.task_id,
        remaining_budget_usd=float((stats.limit or 0) - (stats.spent + cost)),
        warning=None,
    )
```

**Deliverables:**
- Cost recording tool with budget enforcement
- Full integration with CostTracker finalize_spending workflow
- Error handling for budget exceeded scenarios
- Test coverage >90%

**Estimate**: 4-5 hours

---

### Phase 1 Success Criteria ✅
- [ ] All 3 cost tools implemented and tested
- [ ] Tools correctly integrate with MR-Krabs CostTracker
- [ ] Budget enforcement working (prevents overspending)
- [ ] End-to-end test: estimate → execute → record flow
- [ ] Tool documentation with examples in `/docs/MCP_TOOLS.md`

---

## 🤖 Phase 2: CrewAI Orchestration Tools (Weeks 4-5)

### Objective
Expose full CrewAI multi-agent workflow capabilities via MCP tools.

### User Stories

#### P2-S1: Create and Execute Multi-Agent Crew
**As a** higher-level agent with complex user request  
**I want to** create a multi-agent crew workflow without importing CrewAI directly  
**So that** I can orchestrate specialized agents for different subtasks

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_crew_create` accepts agents, tasks, and budget config
- [ ] Returns crew execution ID for tracking
- [ ] Validates agent/task configurations
- [ ] Supports all CrewAI process types (sequential, hierarchical)
- [ ] Integrates automatic cost tracking from Phase 1

**Tool Schema:**
```python
class AgentConfig(BaseModel):
    role: str = Field(..., description="Agent role (e.g., 'Researcher', 'Coder')")
    goal: str = Field(..., description="Agent's objective")
    backstory: str = Field(default="", description="Optional backstory for role-playing")
    tools: list[str] = Field(default_factory=list, description="Optional tool names")

class TaskConfig(BaseModel):
    description: str = Field(..., description="What the agent should do")
    expected_output: str = Field(..., description="Expected result format")
    agent_role: str = Field(..., description="Which agent role handles this task")

class CrewCreateRequest(BaseModel):
    agents: list[AgentConfig] = Field(..., min_length=1)
    tasks: list[TaskConfig] = Field(..., min_length=1)
    process: str = Field(default="sequential", description="Execution process type")
    budget_limit: float | None = Field(default=None, description="Maximum cost for crew execution")
    verbose: bool = Field(default=False, description="Enable detailed logging")

class CrewCreateResponse(BaseModel):
    crew_id: str
    status: str = "created"  # created, executing, completed, failed
    estimated_cost: float
    agents_count: int
    tasks_count: int

@mcp_mrkrabs.tool()
async def crew_create(
    ctx, 
    request: CrewCreateRequest
) -> CrewCreateResponse:
    """Create and execute a multi-agent crew workflow"""
    from src.core.crewai_integration import CostAwareCrew, CostAwareAgent, CostAwareTask
    
    # Convert request to MR-Krabs objects
    agents = [
        CostAwareAgent(
            role=agent.role,
            goal=agent.goal,
            backstory=agent.backstory,
        )
        for agent in request.agents
    ]
    
    tasks = [
        CostAwareTask(
            description=task.description,
            expected_output=task.expected_output,
            agent=agents[request.tasks.index(task)],  # Simplified mapping
        )
        for task in request.tasks
    ]
    
    # Create crew
    import uuid
    crew_id = f"crew-{uuid.uuid4().hex[:8]}"
    
    crew = CostAwareCrew(
        tasks=tasks,
        agents=agents,
        cost_tracker=CostTracker(),
        cost_limit=Decimal(str(request.budget_limit)) if request.budget_limit else None,
    )
    
    # Estimate cost (rough estimate based on task complexity)
    estimated_cost = len(tasks) * 0.15  # ~$0.15 per task average
    
    return CrewCreateResponse(
        crew_id=crew_id,
        status="created",
        estimated_cost=estimated_cost,
        agents_count=len(request.agents),
        tasks_count=len(request.tasks),
    )
```

**Deliverables:**
- Crew creation tool with validation
- Integration with CostAwareCrew
- Support for sequential process (hierarchical in future)

**Estimate**: 6-8 hours

---

#### P2-S2: Execute Crew and Retrieve Results
**As a** higher-level agent that created a crew  
**I want to** execute the crew and get results with cost information  
**So that** I can provide users with both output and cost transparency

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_crew_execute` takes crew_id and runs workflow
- [ ] Returns execution result, cost, and token usage
- [ ] Handles budget exceeded errors gracefully
- [ ] Supports async execution with status polling (optional)
- [ ] Logs execution details for debugging

**Tool Schema:**
```python
class CrewExecuteRequest(BaseModel):
    crew_id: str = Field(..., description="ID of crew to execute")
    inputs: dict = Field(default_factory=dict, description="Optional contextual inputs")

class CrewExecuteResponse(BaseModel):
    crew_id: str
    status: str  # completed, failed
    output: str | None
    cost_usd: float
    tokens_used: dict
    error: str | None = None
    execution_time_seconds: float

@mcp_mrkrabs.tool()
async def crew_execute(ctx, request: CrewExecuteRequest) -> CrewExecuteResponse:
    """Execute a previously created crew workflow"""
    import time
    
    # Retrieve crew from session state
    crew = get_crew_from_session(request.crew_id)
    if not crew:
        raise ValueError(f"Crew {request.crew_id} not found")
    
    start_time = time.time()
    
    try:
        # Execute crew (this triggers automatic cost tracking via callbacks!)
        result = crew.kickoff()
        
        return CrewExecuteResponse(
            crew_id=request.crew_id,
            status="completed",
            output=str(result.get("output", ""))[:10000],  # Truncate very long outputs
            cost_usd=result.get("cost", 0),
            tokens_used=result.get("tokens", {}),
            execution_time_seconds=time.time() - start_time,
        )
        
    except BudgetExceededError as e:
        return CrewExecuteResponse(
            crew_id=request.crew_id,
            status="failed",
            output=None,
            cost_usd=0,  # Or partial cost if available
            tokens_used={},
            error=f"Budget exceeded: {str(e)}",
            execution_time_seconds=time.time() - start_time,
        )
```

**Deliverables:**
- Crew execution tool with cost tracking
- Error handling for budget exceeded and other failures
- Session management to store crew objects between calls

**Estimate**: 5-6 hours

---

#### P2-S3: Execute Single Agent Task (Simpler Alternative)
**As a** higher-level agent with simple request  
**I want to** execute a single agent task without full crew complexity  
**So that** I can quickly get answers for straightforward questions

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_agent_execute` runs single agent on task
- [ ] Simpler interface than full crew (no multi-agent orchestration)
- [ ] Still includes cost tracking and budget enforcement
- [ ] Returns output + cost in single call
- [ ] Supports different agent roles for different capabilities

**Tool Schema:**
```python
class AgentExecuteRequest(BaseModel):
    role: str = Field(default="assistant", description="Agent role")
    task: str = Field(..., description="Task to execute")
    context: str = Field(default="", description="Additional context")
    budget_limit: float | None = Field(default=None, description="Cost limit for this task")

class AgentExecuteResponse(BaseModel):
    output: str
    cost_usd: float
    tokens_used: dict
    role_used: str

@mcp_mrkrabs.tool()
async def agent_execute(ctx, request: AgentExecuteRequest) -> AgentExecuteResponse:
    """Execute a single agent task with cost tracking"""
    from src.core.orchestrator import Orchestrator
    
    orchestrator = Orchestrator()
    
    # Use ask() API with cost tracking
    result = orchestrator.ask(
        prompt=request.task,
        context=request.context,
        budget_limit=Decimal(str(request.budget_limit)) if request.budget_limit else None,
    )
    
    return AgentExecuteResponse(
        output=result["answer"],
        cost_usd=result["cost"],
        tokens_used={"prompt": result["tokens"]["prompt"], "completion": result["tokens"]["completion"]},
        role_used=request.role,
    )
```

**Deliverables:**
- Simple single-agent execution tool
- Full cost tracking integration
- Use case examples in documentation

**Estimate**: 3-4 hours

---

### Phase 2 Success Criteria ✅
- [ ] All 3 CrewAI/agent tools implemented and tested
- [ ] Full end-to-end flow: create crew → execute → get result + cost
- [ ] Session management works across multiple tool calls
- [ ] Cost tracking automatically records all LLM usage
- [ ] Test suite with mock CrewAI workflows

---

## 📊 Phase 3: Analytics & Reporting Tools (Weeks 6-7)

### Objective
Provide analytics, reporting, monitoring capabilities, and production-ready documentation for cost optimization insights.

### User Stories

#### P3-S1: Get Daily Cost Report
**As a** user managing AI costs  
**I want to** see today's spending summary with breakdown by category  
**So that** I can monitor my budget usage and identify trends

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_report_daily` returns daily cost summary
- [ ] Breaks down costs by model, category, tier
- [ ] Shows budget vs actual comparison
- [ ] Includes success rates and escalation statistics
- [ ] Returns human-readable format for agent to present to user

**Deliverables:**
- Daily report tool with comprehensive breakdown
- Integration with existing reporting infrastructure
- Formatted output suitable for user presentation

**Estimate**: 4-5 hours

---

#### P3-S2: Export Cost Data (CSV/JSON)
**As a** user who wants to analyze costs externally  
**I want to** export cost data in CSV or JSON format  
**So that** I can use spreadsheets, BI tools, or custom analytics

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_export_costs` supports CSV and JSON formats
- [ ] Allows filtering by date range, category, model
- [ ] Returns file path or inline data for small exports
- [ ] Includes all relevant fields (timestamp, cost, tokens, model, task)
- [ ] Handles large datasets efficiently

**Deliverables:**
- Export tool with multiple format support
- Integration with CostTracker export functionality
- Test cases for various filter combinations

**Estimate**: 3-4 hours

---

#### P3-S3: Get Efficiency Metrics
**As a** developer optimizing AI workflows  
**I want to** see efficiency metrics like success rates and escalation patterns  
**So that** I can identify which tasks need better tier assignment

**Acceptance Criteria:**
- [ ] Tool `mcp_mrkrabs_analytics_efficiency` returns performance metrics
- [ ] Shows success rate by tier (L0, L1, L2, L3)
- [ ] Displays average escalation depth
- [ ] Identifies tasks that consistently escalate
- [ ] Suggests tier optimization opportunities

**Deliverables:**
- Efficiency analytics tool
- Integration with MetricsCollector
- Actionable insights in response

**Estimate**: 4-5 hours

---

### Phase 3 Success Criteria ✅
- [ ] All 4 stories implemented and tested
- [ ] Reports integrate with existing MR-Krabs metrics infrastructure
- [ ] Export functionality works for large datasets (1000+ entries)
- [ ] Efficiency insights are actionable and accurate
- [ ] Production-ready documentation complete

---

#### P3-S4: Create Production-Ready Documentation
**As a** developer integrating MR-Krabs MCP tools  
**I want to** comprehensive documentation with examples and API reference  
**So that** I can quickly understand and use all MCP capabilities

**Acceptance Criteria:**
- [ ] Create `/docs/MCP_SERVER.md` - Main architecture and usage guide
- [ ] Create `/docs/MCP_TOOLS_REFERENCE.md` - Complete tool schema reference
- [ ] Include HTTP API examples (curl, Python requests)
- [ ] Document session management patterns (stateful vs stateless)
- [ ] Explain budget enforcement modes with examples
- [ ] Provide troubleshooting section for common issues
- [ ] Architecture diagrams showing data flow

**Documentation Structure:**
```markdown
# MCP Server Documentation

## Overview
- What is MR-Krabs MCP Server
- Key features (cost tracking, CrewAI orchestration, etc.)
- Use cases and when to use

## Quickstart
- Installation and setup
- Running the server locally
- First API call example

## Session Management
- Stateful mode (recommended)
- Stateless mode (simple operations)
- Session lifecycle and TTL

## Budget Enforcement Modes
- notify_only: Warn but continue
- fail: Immediately stop on budget exceed
- notify_then_fail: Warn at threshold, fail at 100%
- fail_with_notification: Detailed error on failure

## Tool Reference
- See /docs/MCP_TOOLS_REFERENCE.md for complete API docs

## Examples
- Python integration examples
- cURL command examples
- Real-world workflow scenarios

## Troubleshooting
- Common errors and solutions
- Debug mode and logging
- Performance tips
```

**Deliverables:**
- `/docs/MCP_SERVER.md` - Complete main documentation
- `/docs/MCP_TOOLS_REFERENCE.md` - Tool reference with schemas
- Example code snippets in documentation
- Architecture diagram (text-based or SVG)

**Estimate**: 5-6 hours

---

## 🛡️ Phase 4: Production Hardening (Week 8)

### Objective
Add security, authentication, comprehensive documentation, and deployment tooling.

### User Stories

#### P4-S1: Add Authentication & Authorization
**As a** deployment admin  
**I want to** secure the MCP server with authentication  
**So that** only authorized agents can access cost tracking and execution tools

**Acceptance Criteria:**
- [ ] Support API key authentication via environment variable or config
- [ ] Validate API keys before processing tool calls
- [ ] Log all authenticated requests for audit trail
- [ ] Provide clear error messages for auth failures
- [ ] Document authentication setup in deployment guide

**Deliverables:**
- Authentication middleware for MCP server
- API key generation script
- Security documentation

**Estimate**: 3-4 hours

---

#### P4-S2: Finalize Documentation & Create Examples
**As a** higher-level agent developer  
**I want to** clear documentation on how to use MR-Krabs MCP tools  
**So that** I can integrate them quickly without reverse-engineering

**Acceptance Criteria:**
- [ ] Complete tool reference with schema definitions (created in Phase 3)
- [ ] Usage examples for each tool (Python, shell, curl)
- [ ] Architecture diagram showing data flow
- [ ] Troubleshooting guide for common issues
- [ ] Quickstart tutorial: "Integrate MR-Krabs in 5 minutes"
- [ ] API reference with request/response examples

**Deliverables:**
- `/docs/MCP_SERVER.md` - Main documentation (finalized)
- `/docs/MCP_TOOLS_REFERENCE.md` - Tool schemas and examples (finalized)
- `/examples/mcp_integration.py` - Working integration example
- `/examples/mcp_quickstart.py` - Minimal working example
- README updates with MCP section

**Note**: Core documentation created in Phase 3, finalized here with additional examples and troubleshooting.

**Estimate**: 3-4 hours

---

#### P4-S3: Create Deployment Scripts (Native Python)
**As a** DevOps engineer  
**I want to** easily deploy the MR-Krabs MCP server as a native Python script  
**So that** it can run as a standalone service for multiple agents

**Acceptance Criteria:**
- [ ] Run script for stdio and HTTP server modes
- [ ] Systemd service file for Linux deployment (optional)
- [ ] Scripts for running as daemon or foreground process
- [ ] Health check endpoint for monitoring
- [ ] Environment variable documentation for configuration
- [ ] **Note**: Docker support deferred to Phase 5

**Deliverables:**
- `/scripts/run_mcp_server.sh` - Run script with options
- `/scripts/mrkrabs-mcp-server.service` - Systemd service example
- Deployment guide in `/docs/DEPLOYMENT.md`
- Environment variable reference

**Estimate**: 2-3 hours

---

#### P5-S1: Docker Support (Future Phase)
**As a** DevOps engineer  
**I want to** deploy the MR-Krabs MCP server in Docker containers  
**So that** it can be easily containerized and orchestrated

**Acceptance Criteria:**
- [ ] Multi-stage Dockerfile with minimal image size
- [ ] docker-compose.yml for local development and deployment
- [ ] Health check endpoint for container orchestration
- [ ] Environment variable documentation for container config
- [ ] Kubernetes manifests (optional)

**Deliverables:**
- `Dockerfile` and `docker-compose.yml`
- Container deployment guide
- Example Kubernetes manifests

**Estimate**: 3-4 hours

**Note**: This story moved to Phase 5 (Future) per user requirements - native Python deployment first.

---

#### P4-S4: Integration Tests with Real MCP Client
**As a** quality assurance engineer  
**I want to** test the MCP server with real MCP clients  
**So that** I can verify it works end-to-end before deployment

**Acceptance Criteria:**
- [ ] Test suite using native MCP client (from `native-mcp` skill)
- [ ] Integration tests covering all tool categories
- [ ] Performance tests for concurrent requests
- [ ] Error handling validation (invalid inputs, budget exceeded, etc.)
- [ ] CI/CD pipeline integration

**Deliverables:**
- `/tests/mcp/test_integration.py` - Full integration test suite
- GitHub Actions workflow for MCP server tests
- Performance benchmark results

**Estimate**: 5-6 hours

---

### Phase 4 Success Criteria ✅
- [ ] Authentication working and secure
- [ ] Comprehensive documentation with examples
- [ ] Docker deployment tested and working
- [ ] Full integration test suite passing (>90% coverage)
- [ ] CI/CD pipeline automated

---

## 📋 Complete Implementation Checklist

### All Phases Summary

#### Phase 0: Foundation ✅ (Week 1)
- [ ] P0-S1: Define MCP server architecture
- [ ] P0-S2: Implement basic MCP server skeleton
- [ ] P0-S3: Define configuration & state management strategy

#### Phase 1: Core Cost Tools ✅ (Weeks 2-3)
- [ ] P1-S1: Estimate cost before execution
- [ ] P1-S2: Check remaining budget
- [ ] P1-S3: Track actual spending

#### Phase 2: CrewAI Orchestration ✅ (Weeks 4-5)
- [ ] P2-S1: Create and execute multi-agent crew
- [ ] P2-S2: Execute crew and retrieve results
- [ ] P2-S3: Execute single agent task

#### Phase 3: Analytics & Reporting ✅ (Weeks 6-7)
- [ ] P3-S1: Get daily cost report
- [ ] P3-S2: Export cost data (CSV/JSON)
- [ ] P3-S3: Get efficiency metrics

#### Phase 4: Production Hardening ✅ (Week 8)
- [ ] P4-S1: Add authentication & authorization
- [ ] P4-S2: Create comprehensive documentation
- [ ] P4-S3: Create deployment scripts & Docker support
- [ ] P4-S4: Integration tests with real MCP client

---

## 🎯 Success Metrics

### Technical Metrics
- **Test Coverage**: >90% for all MCP server code
- **Tool Response Time**: <500ms for cost tools, <30s for crew execution
- **Error Rate**: <1% for valid requests
- **Concurrent Sessions**: Support 10+ concurrent agent sessions

### Adoption Metrics (Post-Launch)
- **Integration Time**: <30 minutes to integrate into higher-level agent
- **Tool Usage**: All tools used in production workflows within 2 weeks
- **Cost Savings**: Demonstrate 40%+ cost reduction vs non-optimized execution

---

## 🚀 Post-MCP-Future Enhancements (Out of Scope for This Plan)

### Phase 5: Advanced Features
- ML-based tier recommendation as tool
- Predictive cost forecasting tool
- Multi-tenant support for team deployments
- Plugin system for custom tools

### Phase 6: Community & Ecosystem
- Publish to MCP server registry
- Create example integrations (Cursor, Claude Code, etc.)
- Community contribution guidelines
- Feature requests from user feedback

---

## 📝 Next Steps

### Immediate Actions (Phase 0)
1. Review and approve this implementation plan
2. Set up development environment
3. Begin with P0-S1: Define MCP server architecture
4. Create initial tool schema designs

### Recommended Starting Point
**Start with P0-S1** - The architecture design will inform all subsequent implementation decisions. Once approved, we can move quickly through the phases.

---

## 💡 Key Design Decisions - CONFIRMED

All design decisions have been finalized based on user requirements:

### ✅ Transport: HTTP (Local + Remote)
- **Decision**: HTTP transport supporting both local and remote access
- **Rationale**: Enables flexibility for development (local) and production (remote) deployments
- **Implementation**: Use `httpx` or FastAPI-based MCP server with configurable host/port
- **Default**: `localhost:8000` for local, configurable via environment variables

### ✅ Session Management: Stateful with Stateless Option
- **Decision**: Primary mode is stateful (maintains session state across tool calls)
- **Fallback**: Support fully stateless mode for simple one-off operations
- **Implementation**: 
  - Session-based config: `mcp_mrkrabs_init_session()` returns session_id
  - Stateless tools accept full config in each call as optional override
  - Server maintains in-memory session store with TTL (default 1 hour)

### ✅ Budget Enforcement: Configurable Modes
- **Decision**: Four enforcement modes supported
  1. `notify_only` - Warn but continue execution
  2. `fail` - Immediately fail when budget exceeded
  3. `notify_then_fail` - Warn on threshold (e.g., 80%), fail on exceed
  4. `fail_with_notification` - Fail and provide detailed notification
- **Default**: `notify_then_fail` at 80% threshold, hard fail at 100%
- **Configurable**: Per-session or global via config file

### ✅ Authentication: Optional Initially
- **Decision**: Auth not required for Phase 1-3
- **Rationale**: Enable quick development and local testing
- **Future**: Add API key auth in Phase 4 (Production Hardening)
- **Implementation**: Environment variable `MCP_API_KEY` optional, validates if present

### ✅ Deployment: Native Python First
- **Decision**: Start with native Python script deployment
- **Rationale**: Lower barrier to entry, easier debugging
- **Future**: Docker support in Phase 5 (Advanced Features)
- **Implementation**: `python -m src.mcp.server` or `mrkrabs-mcp-server` CLI

### ✅ Tool Naming: `mcp_mrkrabs_*` Prefix Confirmed
- **Decision**: All tools prefixed with `mcp_mrkrabs_`
- **Rationale**: Clear namespace separation, prevents conflicts
- **Structure**:
  - `mcp_mrkrabs_cost_*` - Cost estimation and tracking
  - `mcp_mrkrabs_budget_*` - Budget management
  - `mcp_mrkrabs_crew_*` - CrewAI orchestration
  - `mcp_mrkrabs_agent_*` - Single agent execution
  - `mcp_mrkrabs_session_*` - Session lifecycle
  - `mcp_mrkrabs_analytics_*` - Reporting and metrics

### ✅ Documentation: Production-Ready Now
- **Decision**: Comprehensive docs included in Phase 1-3
- **Scope**: Tool reference, examples, architecture, troubleshooting
- **Deferred**: Docker deployment guide (Phase 5), advanced auth patterns (Phase 4)
- **Deliverables**:
  - `/docs/MCP_SERVER.md` - Main documentation
  - `/docs/MCP_TOOLS_REFERENCE.md` - Complete tool schemas
  - `/examples/mcp_quickstart.py` - Working integration examples
  - README updates with MCP section

---

**Document Version**: 1.0  
**Last Updated**: May 5, 2026  
**Status**: Ready for Review
