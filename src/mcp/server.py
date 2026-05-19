"""
MR-Krabs MCP Server - HTTP Implementation

FastAPI-based MCP server exposing MR-Krabs capabilities as tools.
Supports both stateful (session-based) and stateless operation modes.

Usage:
    python -m src.mcp.server
    
Environment Variables:
    MCP_HOST: Server host (default: 0.0.0.0)
    MCP_PORT: Server port (default: 8000)
    SESSION_TTL: Session time-to-live in seconds (default: 3600)
    MCP_API_KEY: Optional API key for authentication
"""

import os
import time as _time
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import structlog

from .session_manager import SessionManager, SessionConfig
from .budget_enforcer import BudgetEnforcer, EnforcementMode, BudgetCheckResult
from .cost_tools import (
    CostEstimateRequest,
    CostEstimateResponse,
    BudgetCheckRequest,
    BudgetCheckResponse,
    CostTrackRequest,
    CostTrackResponse,
    process_cost_estimate,
    process_cost_track,
)

# Phase 2: CrewAI Orchestration Tools
from .crew_tools import (
    CrewCreateRequest,
    CrewCreateResponse,
    CrewExecuteRequest,
    CrewExecuteResponse,
    AgentExecuteRequest,
    AgentExecuteResponse,
    process_crew_create,
    process_crew_execute,
    process_agent_execute,
)

# Phase 3: Analytics & Observability Tools
from .analytics_tools import (
    AnalyticsSummaryRequest,
    AnalyticsSummaryResponse,
    TierBreakdownRequest,
    TierBreakdownResponse,
    CostTrendsRequest,
    CostTrendsResponse,
    EfficiencyReportRequest,
    EfficiencyReportResponse,
    ExportRequest,
    ExportResponse,
    process_analytics_summary,
    process_tier_breakdown,
    process_cost_trends,
    process_efficiency_report,
    process_export_csv,
    process_export_json,
)

# Initialize logger
log = structlog.get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="MR-Krabs MCP Server",
    version="0.1.0-dev",
    description=(
        "Model Context Protocol server for MR-Krabs cost-optimized AI orchestration. "
        "Exposes cost tracking, budget management, and CrewAI orchestration as reusable tools."
    ),
)

# ---- Phase 3: Bearer Token Authentication ----
from .auth import create_auth_middleware
from starlette.middleware.base import BaseHTTPMiddleware

_auth_enabled = os.getenv("MRKRABS_ENABLE_BEARER_AUTH", "false").lower() == "true"
if _auth_enabled:
    middleware = create_auth_middleware(enabled=True)
    app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.dispatch)
    log.info("Bearer token authentication enabled")

# Initialize session manager with configurable TTL
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))
session_manager = SessionManager(ttl_seconds=SESSION_TTL)


# ==================== Request/Response Models ====================

class PingRequest(BaseModel):
    """Request model for ping endpoint."""
    session_id: Optional[str] = None


class PingResponse(BaseModel):
    """Response model for ping endpoint."""
    status: str
    message: str
    session_active: Optional[bool] = None


class SessionInitRequest(BaseModel):
    """Request model for session initialization."""
    budget_limit: Optional[float] = Field(default=10.0, description="Daily budget limit in USD")
    enforcement_mode: str = Field(
        default="notify_then_fail",
        description="Budget enforcement mode: notify_only, fail, notify_then_fail, fail_with_notification"
    )
    warning_threshold: float = Field(default=80.0, description="Warning threshold percentage")
    default_tier: str = Field(default="L0", description="Default tier for escalation")
    models: List[str] = Field(default=["google/gemma-7b-it"], description="Allowed LLM models")


class SessionInitResponse(BaseModel):
    """Response model for session initialization."""
    session_id: str
    status: str
    config: Dict[str, Any]
    message: str


class SessionStatusResponse(BaseModel):
    """Response model for session status."""
    session_id: str
    active: bool
    config: Optional[Dict[str, Any]] = None
    time_remaining_seconds: Optional[float] = None
    budget_limit: Optional[float] = None
    remaining_budget: Optional[float] = None
    spent: Optional[float] = 0.0
    message: Optional[str] = None


class SessionCloseResponse(BaseModel):
    """Response model for session close."""
    session_id: str
    closed: bool
    message: str


# ==================== Authentication ====================

# Remove the old verify_api_key function since we're using middleware now


# ==================== Health & Status Endpoints ====================

@app.get("/health", summary="Health check")
async def health_check():
    """
    Health check endpoint.
    
    Returns server status for monitoring and load balancers.
    """
    return {
        "status": "healthy",
        "service": "mr-krabs-mcp",
        "version": "0.1.0-dev",
        "session_count": session_manager.get_session_count(),
    }


@app.get("/ready", summary="Readiness check")
async def readiness_check():
    """Readiness probe — returns 200 when server is ready to accept traffic."""
    return {
        "status": "ready",
        "service": "mr-krabs-mcp",
    }


@app.get("/metrics", summary="Prometheus metrics endpoint")
async def metrics_endpoint(request: Request):
    """
    Prometheus /metrics endpoint.
    
    Returns metrics in Prometheus text format for scraping.
    Requires PrometheusMetricsAdapter to be initialized and enabled.
    Rate-limited: max 1 scrape per 15 seconds per IP.
    """
    from fastapi.responses import Response
    
    # Try to get Prometheus adapter from registry
    try:
        from src.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        adapter = registry.get("prometheus_metrics")
        
        # Simple rate limiting by IP
        client_ip = request.client.host if request and request.client else "unknown"
        now = _time.time()
        if hasattr(adapter, '_scrape_timestamps'):
            last = adapter._scrape_timestamps.get(client_ip, 0)
            if now - last < 15:
                return Response(
                    content="Rate limited: max 1 scrape per 15 seconds\n",
                    status_code=429,
                    media_type="text/plain",
                )
            adapter._scrape_timestamps[client_ip] = now
        
        metrics_text = adapter.get_metrics_text()
        return Response(
            content=metrics_text,
            media_type="text/plain; version=0.0.4",
        )
    except Exception:
        return Response(
            content="# Prometheus metrics not available\n",
            status_code=503,
            media_type="text/plain",
        )


@app.get("/", summary="Root endpoint")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "MR-Krabs MCP Server",
        "version": "0.1.0-dev",
        "description": "Cost-optimized AI orchestration via Model Context Protocol",
        "endpoints": {
            "health": "/health",
            "tools": "/tools",
            "docs": "/docs",
            "sessions": "/sessions"
        }
    }


# ==================== Tools Endpoint ====================

@app.get("/tools", summary="List available tools")
async def list_tools():
    """
    List all available MCP tools.
    
    Returns complete tool registry with categories and descriptions.
    """
    tools = {
        "session": [
            {"name": "mcp_mrkrabs_session_init", "description": "Initialize a new session"},
            {"name": "mcp_mrkrabs_session_status", "description": "Check session status"},
            {"name": "mcp_mrkrabs_session_close", "description": "Close an active session"},
        ],
        "cost": [
            {"name": "mcp_mrkrabs_cost_estimate", "description": "Estimate cost for LLM usage"},
            {"name": "mcp_mrkrabs_cost_track", "description": "Record actual spending"},
            {"name": "mcp_mrkrabs_cost_breakdown", "description": "Get detailed cost breakdown"},
        ],
        "budget": [
            {"name": "mcp_mrkrabs_budget_check", "description": "Check remaining budget"},
            {"name": "mcp_mrkrabs_budget_enforce", "description": "Set enforcement mode"},
            {"name": "mcp_mrkrabs_budget_status", "description": "Get comprehensive budget status"},
        ],
        "crew": [
            {"name": "mcp_mrkrabs_crew_create", "description": "Create multi-agent crew"},
            {"name": "mcp_mrkrabs_crew_execute", "description": "Execute crew workflow"},
            {"name": "mcp_mrkrabs_crew_result", "description": "Retrieve crew execution result"},
        ],
        "agent": [
            {"name": "mcp_mrkrabs_agent_execute", "description": "Execute single agent task"},
            {"name": "mcp_mrkrabs_agent_escalate", "description": "Execute with auto-escalation"},
        ],
        "analytics": [
            {"name": "mcp_mrkrabs_analytics_summary", "description": "Get overall spending summary"},
            {"name": "mcp_mrkrabs_tier_breakdown", "description": "Cost breakdown by tier"},
            {"name": "mcp_mrkrabs_cost_trends", "description": "Cost trend analysis over time"},
            {"name": "mcp_mrkrabs_efficiency_report", "description": "Efficiency metrics and suggestions"},
            {"name": "mcp_mrkrabs_export_csv", "description": "Export analytics to CSV file"},
            {"name": "mcp_mrkrabs_export_json", "description": "Export analytics to JSON file"},
        ],
    }
    
    return {
        "tools": tools,
        "total_count": sum(len(v) for v in tools.values()),
        "categories": list(tools.keys()),
    }


# ==================== Session Management Tools ====================

@app.post("/tools/mcp_mrkrabs_session_init", 
         summary="Initialize session")
async def session_init(request: SessionInitRequest):
    """
    Initialize a new MCP session.
    
    Creates a stateful session with the provided configuration.
    Returns session_id for use in subsequent tool calls.
    
    Example:
        POST /tools/mcp_mrkrabs_session_init
        {
            "budget_limit": 10.0,
            "enforcement_mode": "notify_then_fail"
        }
    """
    try:
        # Create session with config
        config_dict = request.model_dump(exclude_unset=True)
        session_id = session_manager.create_session(config=config_dict)
        
        log.info(f"Session created", session_id=session_id, **config_dict)
        
        return SessionInitResponse(
            session_id=session_id,
            status="active",
            config=config_dict,
            message=f"Session created successfully. TTL: {SESSION_TTL} seconds",
        )
    except Exception as e:
        log.error(f"Failed to create session", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@app.get("/tools/mcp_mrkrabs_session_status/{session_id}",
         summary="Get session status")
async def session_status(session_id: str):
    """
    Check the status of a session.
    
    Returns session configuration and time remaining before expiration.
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        return SessionStatusResponse(
            session_id=session_id,
            active=False,
            message="Session not found or expired",
        )
    
    import time
    time_remaining = max(0, session.ttl_seconds - (time.time() - session.last_accessed))
    
    return SessionStatusResponse(
        session_id=session_id,
        active=True,
        config=session.to_dict(),
        time_remaining_seconds=time_remaining,
        budget_limit=session.budget_limit,
        remaining_budget=session.remaining_budget,
        spent=session.spent,
    )


@app.delete("/tools/mcp_mrkrabs_session_close/{session_id}",
            summary="Close session")
async def session_close(session_id: str):
    """
    Close and delete a session.
    
    Cleans up session resources immediately rather than waiting for TTL expiration.
    """
    deleted = session_manager.delete_session(session_id)
    
    return SessionCloseResponse(
        session_id=session_id,
        closed=deleted,
        message="Session closed" if deleted else "Session not found",
    )


# ==================== Ping/Health Tool ====================

@app.post("/tools/mcp_mrkrabs_ping", 
          summary="Ping server")
async def ping(request: PingRequest):
    """
    Test MCP connectivity.
    
    Verifies server is running and optionally validates session.
    """
    session_active = None
    
    if request.session_id:
        session = session_manager.get_session(request.session_id)
        session_active = session is not None
    
    return PingResponse(
        status="ok",
        message="MR-Krabs MCP server is running!",
        session_active=session_active,
    )


# ==================== Cost Management Tools (Phase 1) ====================

@app.post("/tools/mcp_mrkrabs_cost_estimate", 
          summary="Estimate LLM cost")
async def cost_estimate(request: CostEstimateRequest):
    """
    Estimate the cost of LLM usage.
    
    Supports both stateful (session_id) and stateless (config) modes.
    
    Example (stateless):
        POST /tools/mcp_mrkrabs_cost_estimate
        {
            "model": "google/gemma-7b-it",
            "input_tokens": 100,
            "output_tokens": 50
        }
    
    Example (with text):
        POST /tools/mcp_mrkrabs_cost_estimate
        {
            "model": "meta-llama/llama-3-8b-instruct",
            "prompt_text": "Write a poem about AI"
        }
    """
    try:
        # Process the estimate
        result = process_cost_estimate(request)
        
        log.info(
            f"Cost estimated",
            session_id=request.session_id,
            model=request.model,
            estimated_cost=result.estimated_cost,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to estimate cost", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cost estimation failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_budget_check", 
          summary="Check budget availability")
async def budget_check(request: BudgetCheckRequest):
    """
    Check if a spending operation can proceed within budget.
    
    Enforces budget limits based on the session's enforcement mode.
    
    Example (stateful):
        POST /tools/mcp_mrkrabs_budget_check
        {
            "session_id": "session-abc123",
            "would_spend": 2.50
        }
    
    Example (stateless):
        POST /tools/mcp_mrkrabs_budget_check
        {
            "config": {"budget_limit": 10.0, "enforcement_mode": "fail"},
            "would_spend": 2.50
        }
    """
    try:
        # Get session or use default config
        if request.session_id:
            session = session_manager.get_session(request.session_id)
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found or expired"
                )
            
            enforcer = BudgetEnforcer(
                budget_limit=session.budget_limit,
                enforcement_mode=session.enforcement_mode,
                warning_threshold=session.warning_threshold,
                spent=session.spent,  # Pass accumulated spending for accurate check
            )
        elif request.config:
            # Stateless mode
            enforcer = BudgetEnforcer(
                budget_limit=request.config.get("budget_limit", 10.0),
                enforcement_mode=request.config.get("enforcement_mode", "notify_then_fail"),
                warning_threshold=request.config.get("warning_threshold", 80.0),
            )
        else:
            # Default session-less mode
            enforcer = BudgetEnforcer()
        
        # Check budget
        check_result = enforcer.check_budget(would_spend=request.would_spend)
        
        return BudgetCheckResponse(
            can_proceed=check_result.can_proceed,
            status=check_result.to_dict(),
            session_id=request.session_id,
            warning=check_result.warning,
            error=check_result.error,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to check budget", error=str(e))
        raise HTTPException(status_code=500, detail=f"Budget check failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_cost_track", 
          summary="Record actual spending")
async def cost_track(request: CostTrackRequest):
    """
    Record actual spending for a session.
    
    Tracks real costs incurred from LLM usage.
    
    Example:
        POST /tools/mcp_mrkrabs_cost_track
        {
            "session_id": "session-abc123",
            "amount": 0.05,
            "model": "google/gemma-7b-it",
            "input_tokens": 100,
            "output_tokens": 50
        }
    """
    try:
        # Validate session if provided
        if request.session_id:
            session = session_manager.get_session(request.session_id)
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found or expired"
                )
            
            # Check if this spending is allowed
            enforcer = BudgetEnforcer(
                budget_limit=session.budget_limit,
                enforcement_mode=session.enforcement_mode,
                warning_threshold=session.warning_threshold,
                spent=session.spent,  # Pass accumulated spending for accurate check
            )
            
            check_result = enforcer.check_budget(would_spend=request.amount)
            if not check_result.can_proceed:
                raise HTTPException(
                    status_code=409,
                    detail=check_result.error or "Budget enforcement denied"
                )
        
        # Process the tracking
        result = process_cost_track(request)
        
        # Update session spending if session_id provided
        if request.session_id:
            session = session_manager.get_session(request.session_id)
            if session:
                session.add_spent(request.amount)
        
        log.info(
            f"Cost tracked",
            session_id=request.session_id,
            amount=request.amount,
            model=request.model,
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to track cost", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cost tracking failed: {str(e)}")


# ==================== CrewAI Orchestration Tools (Phase 2) ====================

@app.post("/tools/mcp_mrkrabs_crew_create", 
          summary="Create CrewAI crew")
async def crew_create(request: CrewCreateRequest):
    """
    Create and validate a CrewAI multi-agent crew.
    
    Supports both stateful (session_id) and stateless (config) modes.
    
    Example:
        POST /tools/mcp_mrkrabs_crew_create
        {
            "crew_config": {
                "name": "research-crew",
                "agents": [
                    {
                        "name": "researcher",
                        "role": "Senior Researcher",
                        "goal": "Conduct thorough research on any topic",
                        "backstory": "You are an expert researcher with years of experience"
                    },
                    {
                        "name": "writer",
                        "role": "Content Writer",
                        "goal": "Write engaging content based on research",
                        "backstory": "You are a skilled writer who transforms data into compelling stories"
                    }
                ],
                "tasks": [
                    {
                        "description": "Research the latest trends in AI",
                        "agent_name": "researcher",
                        "expected_output": "A comprehensive report on AI trends"
                    },
                    {
                        "description": "Write an article based on the research",
                        "agent_name": "writer",
                        "expected_output": "A well-written article about AI trends"
                    }
                ]
            }
        }
    """
    try:
        result = process_crew_create(request)
        
        log.info(
            f"Crew created",
            session_id=request.session_id,
            crew_id=result.crew_id,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to create crew", error=str(e))
        raise HTTPException(status_code=500, detail=f"Crew creation failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_crew_execute", 
          summary="Execute CrewAI crew")
async def crew_execute(request: CrewExecuteRequest):
    """
    Execute a CrewAI multi-agent crew workflow.
    
    Creates and runs the crew, returning the final output.
    
    Example:
        POST /tools/mcp_mrkrabs_crew_execute
        {
            "crew_config": {
                "name": "writing-crew",
                "agents": [...],
                "tasks": [...]
            },
            "config": {
                "model": "google/gemma-7b-it"
            }
        }
    """
    try:
        result = process_crew_execute(request)
        
        log.info(
            f"Crew executed",
            session_id=request.session_id,
            success=result.success,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to execute crew", error=str(e))
        raise HTTPException(status_code=500, detail=f"Crew execution failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_agent_execute", 
          summary="Execute single agent task")
async def agent_execute(request: AgentExecuteRequest):
    """
    Execute a single agent task with MR-Krabs cost optimization.
    
    Ideal for simple tasks that don't require multi-agent coordination.
    
    Example:
        POST /tools/mcp_mrkrabs_agent_execute
        {
            "prompt": "Write a poem about AI in the style of Shakespeare",
            "model": "meta-llama/llama-3-8b-instruct"
        }
    """
    try:
        result = process_agent_execute(request)
        
        log.info(
            f"Agent executed task",
            session_id=request.session_id,
            success=result.success,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to execute agent task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")


# ==================== Analytics Tools (Phase 3) ====================

@app.post("/tools/mcp_mrkrabs_analytics_summary", 
          summary="Get analytics summary")
async def analytics_summary(request: AnalyticsSummaryRequest):
    """
    Get overall spending summary and efficiency metrics.
    
    Returns aggregated cost data, task counts, and tier distribution.
    
    Example:
        POST /tools/mcp_mrkrabs_analytics_summary
        {
            "session_id": "session-abc123",
            "period_days": 7,
            "include_breakdown": true
        }
    
    Response includes:
    - total_spent: Total cost for period
    - task_count: Number of tasks executed
    - avg_cost_per_task: Average cost
    - tier_distribution: Breakdown by L0/L1/L2/L3
    - trend_direction: increasing/decreasing/stable
    - efficiency_score: Overall efficiency (0-100)
    """
    try:
        result = process_analytics_summary(request)
        
        log.info(
            "Analytics summary generated",
            session_id=request.session_id,
            period_days=request.period_days,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate analytics summary", error=str(e))
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_tier_breakdown", 
          summary="Get tier cost breakdown")
async def tier_breakdown(request: TierBreakdownRequest):
    """
    Get detailed cost breakdown by tier (L0/L1/L2/L3).
    
    Shows which tiers are being used most and where costs are concentrated.
    
    Example:
        POST /tools/mcp_mrkrabs_tier_breakdown
        {
            "session_id": "session-abc123",
            "period_days": 7
        }
    
    Response includes:
    - tiers: Detailed stats for L0, L1, L2, L3
    - most_used_tier: Tier with highest task count
    - highest_cost_tier: Tier with highest total cost
    - best_efficiency_tier: Tier with best efficiency score
    """
    try:
        result = process_tier_breakdown(request)
        
        log.info(
            "Tier breakdown generated",
            session_id=request.session_id,
            period_days=request.period_days,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate tier breakdown", error=str(e))
        raise HTTPException(status_code=500, detail=f"Tier breakdown failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_cost_trends", 
          summary="Get cost trend analysis")
async def cost_trends(request: CostTrendsRequest):
    """
    Get cost trend analysis over time with ASCII visualization.
    
    Shows daily spending patterns and overall trend direction.
    
    Example:
        POST /tools/mcp_mrkrabs_cost_trends
        {
            "session_id": "session-abc123",
            "period_days": 7
        }
    
    Response includes:
    - trend_direction: increasing/decreasing/stable
    - change_percent: Percentage change over period
    - daily_data: Day-by-day breakdown
    - ascii_chart: Terminal-friendly visualization
    """
    try:
        result = process_cost_trends(request)
        
        log.info(
            "Cost trends generated",
            session_id=request.session_id,
            period_days=request.period_days,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate cost trends", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cost trends failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_efficiency_report", 
          summary="Get efficiency report")
async def efficiency_report(request: EfficiencyReportRequest):
    """
    Get comprehensive efficiency analysis and optimization suggestions.
    
    Provides actionable recommendations for cost optimization.
    
    Example:
        POST /tools/mcp_mrkrabs_efficiency_report
        {
            "session_id": "session-abc123",
            "period_days": 7
        }
    
    Response includes:
    - overall_efficiency_score: Score from 0-100
    - tier_analysis: Efficiency by tier
    - optimization_suggestions: Actionable recommendations
    - potential_monthly_savings: Estimated savings if suggestions implemented
    """
    try:
        result = process_efficiency_report(request)
        
        log.info(
            "Efficiency report generated",
            session_id=request.session_id,
            period_days=request.period_days,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate efficiency report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Efficiency report failed: {str(e)}")


# ==================== Export Tools ====================

@app.post("/tools/mcp_mrkrabs_export_csv", 
          summary="Export analytics to CSV")
async def export_csv(request: ExportRequest):
    """
    Export analytics data to CSV format.
    
    Generates a comprehensive CSV report including:
    - Summary metrics
    - Tier breakdown
    - Daily trends
    - Efficiency analysis
    
    Args:
        request: ExportRequest with period and output options
        
    Returns:
        ExportResponse with file path and data preview
        
    Example:
        POST /tools/mcp_mrkrabs_export_csv
        {
            "period_days": 30,
            "output_dir": "/tmp/reports",
            "output_file": "my_report.csv"
        }
    """
    try:
        result = process_export_csv(request)
        
        log.info(
            "CSV export generated",
            session_id=request.session_id,
            period_days=request.period_days,
            file_path=result.file_path,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate CSV export", error=str(e))
        raise HTTPException(status_code=500, detail=f"CSV export failed: {str(e)}")


@app.post("/tools/mcp_mrkrabs_export_json", 
          summary="Export analytics to JSON")
async def export_json(request: ExportRequest):
    """
    Export analytics data to JSON format.
    
    Generates a comprehensive JSON report including:
    - Summary metrics
    - Tier breakdown
    - Daily trends
    - Efficiency analysis
    
    Args:
        request: ExportRequest with period and output options
        
    Returns:
        ExportResponse with file path and data preview
        
    Example:
        POST /tools/mcp_mrkrabs_export_json
        {
            "period_days": 30,
            "output_dir": "/tmp/reports",
            "output_file": "my_report.json"
        }
    """
    try:
        result = process_export_json(request)
        
        log.info(
            "JSON export generated",
            session_id=request.session_id,
            period_days=request.period_days,
            file_path=result.file_path,
        )
        
        return result
    except Exception as e:
        log.error(f"Failed to generate JSON export", error=str(e))
        raise HTTPException(status_code=500, detail=f"JSON export failed: {str(e)}")


# ==================== Error Handlers ====================

@app.exception_handler(Exception)
async def general_exception_handler(request: Any, exc: Exception):
    """Handle unexpected exceptions. Pass through HTTPExceptions (they're expected)."""
    # Don't intercept HTTPException — FastAPI handles those natively
    if isinstance(exc, HTTPException):
        raise exc
    log.error(f"Unexpected error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ==================== Startup/Shutdown Events ====================

@app.on_event("startup")
async def startup_event():
    """Log server startup."""
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = os.getenv("MCP_PORT", "8000")
    
    log.info(
        "MR-Krabs MCP Server starting",
        host=host,
        port=port,
        session_ttl=SESSION_TTL,
        auth_required=bool(os.getenv("MCP_API_KEY")),
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    # Cleanup expired sessions
    cleaned = session_manager.cleanup_expired()
    log.info(f"Server shutting down", sessions_cleaned=cleaned)


# ==================== Main Entry Point ====================

def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    
    # Import here to avoid circular imports
    from .auth import AuthManager, KeyManager, RateLimiter, AuthMiddleware
    
    auth_manager = AuthManager(secret_key=os.getenv("JWT_SECRET", "change-me"))
    key_manager = KeyManager()
    # Seed with existing MCP_API_KEY if set
    if existing_key := os.getenv("MCP_API_KEY"):
        key_manager.add_key(existing_key, "legacy")
    rate_limiter = RateLimiter(
        max_requests=int(os.getenv("RATE_LIMIT_MAX", "100")),
        window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    )
    app.add_middleware(AuthMiddleware, auth_manager=auth_manager, key_manager=key_manager, rate_limiter=rate_limiter)
    
    return app


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    
    log.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
