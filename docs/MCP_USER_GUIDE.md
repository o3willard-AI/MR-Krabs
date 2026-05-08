# MR-Krabs MCP Server - Complete User Guide

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: Production Ready ✅

---

## 📚 Table of Contents

1. [What is MR-Krabs?](#what-is-mr-krabs)
2. [Quick Start](#quick-start)
3. [Server Configuration](#server-configuration)
4. [Authentication](#authentication)
5. [Session Management](#session-management)
6. [Cost Management Tools](#cost-management-tools)
7. [CrewAI Integration Tools](#crewai-integration-tools)
8. [Analytics & Reporting Tools](#analytics--reporting-tools)
9. [Export Tools](#export-tools)
10. [API Reference](#api-reference)
11. [Examples](#examples)
12. [Troubleshooting](#troubleshooting)

---

## What is MR-Krabs?

MR-Krabs is a **cost-optimized AI orchestrator** that provides intelligent multi-agent workflows with automatic budget enforcement. Through the MCP (Model Context Protocol) server, higher-level agents can leverage these capabilities without understanding the underlying orchestration logic.

### Key Features

✅ **4-Tier Auto-Escalation**: Tasks automatically escalate from cheap (L0) to expensive (L3) models on failure  
✅ **Real-Time Budget Tracking**: Monitor spending with configurable warnings and hard limits  
✅ **CrewAI Integration**: Create and execute multi-agent crews via MCP tools  
✅ **Analytics & Reporting**: Detailed cost breakdowns, efficiency metrics, and trend analysis  
✅ **Encrypted Key Storage**: Secure vault for LLM API keys (Fernet/AES-128-CBC)  
✅ **Session Management**: Stateful or stateless operation modes  

---

## Quick Start

### 1. Start the MCP Server

```bash
cd /home/sblanken/working/code/MR-Krabs
python -m src.mcp.server
```

Server runs on `http://localhost:8000` by default.

### 2. Verify Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "mr-krabs-mcp",
  "session_count": 0
}
```

### 3. Initialize a Session

```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '''{"budget_limit": 10.0, "enforcement_mode": "notify_then_fail"}'''
```

Response:
```json
{
  "success": true,
  "session_id": "sess_abc123",
  "status": "active",
  "config": {
    "budget_limit": 10.0,
    "enforcement_mode": "notify_then_fail"
  }
}
```

### 4. Estimate Cost Before Execution

```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d '''{
    "session_id": "sess_abc123",
    "model": "google/gemma-7b-it",
    "input_tokens": 500,
    "output_tokens": 200
  }'''
```

### 5. Execute a CrewAI Task

```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_execute \
  -H "Content-Type: application/json" \
  -d '''{
    "session_id": "sess_abc123",
    "crew_id": "my-crew",
    "task": "Analyze the sentiment of this product review..."
  }'''
```

### 6. View Analytics

```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_analytics_summary \
  -H "Content-Type: application/json" \
  -d '''{"session_id": "sess_abc123", "period_days": 7}'''
```

---

## Server Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8000` | Port number |
| `SESSION_TTL` | `3600` | Session timeout in seconds (1 hour) |
| `MCP_API_KEY` | *(none)* | Bearer token for authentication (optional) |
| `VAULT_MASTER_KEY_FILE` | `~/.mrkrabs/master.key` | Path to vault encryption key |

### Example: Custom Configuration

```bash
export MCP_HOST="127.0.0.1"
export MCP_PORT="9000"
export SESSION_TTL="7200"  # 2 hours
export MCP_API_KEY="your-secret-key-here"

python -m src.mcp.server
```

---

## Authentication

### Optional Bearer Token

If `MCP_API_KEY` is set, all `/tools/*` endpoints require authentication:

```bash
curl http://localhost:8000/tools \
  -H "Authorization: Bearer your-api-key"
```

### No Authentication Mode

If `MCP_API_KEY` is not set (default), the server accepts requests without auth. Useful for local development or when authentication is handled externally.

---

## Session Management

### Stateful vs Stateless Modes

**Stateful (Recommended)**: Server tracks budget, session state, and history. Use a single `session_id` across multiple tool calls.

**Stateless**: Client manages state. Each request includes full configuration. Useful for fire-and-forget operations.

### Session Lifecycle

#### 1. Create Session

```bash
POST /tools/mcp_mrkrabs_session_init
```

**Request:**
```json
{
  "budget_limit": 25.0,
  "enforcement_mode": "notify_then_fail",
  "warning_threshold": 75.0,
  "default_tier": "L1",
  "models": ["google/gemma-7b-it", "meta-llama/llama-3-8b-instruct"]
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "sess_xyz789",
  "status": "active",
  "config": { ... }
}
```

#### 2. Check Session Status

```bash
GET /tools/mcp_mrkrabs_session_status/{session_id}
```

**Response:**
```json
{
  "active": true,
  "time_remaining_seconds": 3456,
  "budget_spent": 5.23,
  "budget_limit": 25.0,
  "enforcement_mode": "notify_then_fail",
  "task_count": 12
}
```

#### 3. Close Session

```bash
DELETE /tools/mcp_mrkrabs_session_close/{session_id}
```

**Response:**
```json
{
  "closed": true,
  "final_spending": 8.47,
  "total_tasks": 18
}
```

### Enforcement Modes

| Mode | Behavior |
|------|----------|
| `notify_only` | Log warnings but continue execution |
| `fail` | Block immediately when budget exceeded |
| `notify_then_fail` | Warn on first occurrence, then block |
| `fail_with_notification` | Block + send alert (webhook/Slack - future) |

---

## Cost Management Tools

### mcp_mrkrabs_cost_estimate

Estimate the cost of an LLM call before execution.

**Endpoint:** `POST /tools/mcp_mrkrabs_cost_estimate`

**Request Schema:**
```json
{
  "session_id": "string (optional)",
  "model": "string",
  "input_tokens": "number (optional)",
  "output_tokens": "number (optional)",
  "prompt_text": "string (alternative to tokens)"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d '''{
    "model": "openai/gpt-4o",
    "input_tokens": 1000,
    "output_tokens": 500
  }'''
```

**Response:**
```json
{
  "success": true,
  "estimated_cost": 0.025,
  "model": "openai/gpt-4o",
  "input_tokens": 1000,
  "output_tokens": 500
}
```

---

### mcp_mrkrabs_budget_check

Check if a proposed expenditure fits within budget.

**Endpoint:** `POST /tools/mcp_mrkrabs_budget_check`

**Request Schema:**
```json
{
  "session_id": "string",
  "would_spend": "number"
}
```

**Response:**
```json
{
  "success": true,
  "can_proceed": true,
  "remaining_budget": 18.50,
  "budget_limit": 25.0,
  "already_spent": 6.50,
  "would_exceed_by": null
}
```

---

### mcp_mrkrabs_cost_track

Record actual spending against a session.

**Endpoint:** `POST /tools/mcp_mrkrabs_cost_track`

**Request Schema:**
```json
{
  "session_id": "string",
  "amount": "number",
  "model": "string (optional)",
  "description": "string (optional)"
}
```

---

## CrewAI Integration Tools

### mcp_mrkrabs_crew_create

Create a multi-agent crew with cost-optimized execution.

**Endpoint:** `POST /tools/mcp_mrkrabs_crew_create`

**Request Schema:**
```json
{
  "session_id": "string (optional)",
  "crew_config": {
    "agents": [
      {
        "name": "string",
        "role": "string",
        "goal": "string",
        "backstory": "string (optional)"
      }
    ],
    "tasks": [
      {
        "description": "string",
        "expected_output": "string (optional)",
        "agent_name": "string"
      }
    ],
    "verbose": "boolean (default: false)"
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_create \
  -H "Content-Type: application/json" \
  -d '''{
    "session_id": "sess_abc123",
    "crew_config": {
      "agents": [
        {
          "name": "researcher",
          "role": "Research Analyst",
          "goal": "Gather accurate information from reliable sources"
        },
        {
          "name": "writer",
          "role": "Content Writer",
          "goal": "Create well-structured, engaging content"
        }
      ],
      "tasks": [
        {
          "description": "Research the history of artificial intelligence",
          "agent_name": "researcher"
        },
        {
          "description": "Write a summary article based on research findings",
          "agent_name": "writer"
        }
      ]
    }
  }'''
```

**Response:**
```json
{
  "success": true,
  "crew_id": "crew_xyz456",
  "agents_count": 2,
  "tasks_count": 2
}
```

---

### mcp_mrkrabs_crew_execute

Execute a previously created crew.

**Endpoint:** `POST /tools/mcp_mrkrabs_crew_execute`

**Request Schema:**
```json
{
  "session_id": "string (optional)",
  "crew_id": "string",
  "task_override": "string (optional)"
}
```

---

### mcp_mrkrabs_agent_execute

Execute a single agent task without full crew setup.

**Endpoint:** `POST /tools/mcp_mrkrabs_agent_execute`

**Request Schema:**
```json
{
  "session_id": "string (optional)",
  "agent_config": {
    "name": "string",
    "role": "string",
    "goal": "string"
  },
  "task": "string",
  "model_override": "string (optional)"
}
```

---

## Analytics & Reporting Tools

### mcp_mrkrabs_analytics_summary

Get comprehensive cost and performance analytics.

**Endpoint:** `POST /tools/mcp_mrkrabs_analytics_summary`

**Request Schema:**
```json
{
  "session_id": "string (optional)",
  "period_days": "number (default: 7)"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "period": "7 days",
    "total_spent": 45.67,
    "total_tasks": 128,
    "avg_cost_per_task": 0.357,
    "tier_breakdown": {
      "L0": {"tasks": 82, "cost": 8.20},
      "L1": {"tasks": 32, "cost": 24.60},
      "L2": {"tasks": 12, "cost": 9.80},
      "L3": {"tasks": 2, "cost": 3.07}
    },
    "success_rate": 94.5,
    "escalation_rate": 21.1
  }
}
```

---

### mcp_mrkrabs_cost_trend

Get daily cost trend analysis with ASCII chart.

**Endpoint:** `POST /tools/mcp_mrkrabs_cost_trend`

**Response includes:**
- Daily spending breakdown
- Trend analysis (increasing/decreasing/stable)
- Percentage change calculation
- ASCII chart for terminal visualization
- Min/max daily cost tracking

---

### mcp_mrkrabs_efficiency_report

Get efficiency metrics and optimization suggestions.

**Endpoint:** `POST /tools/mcp_mrkrabs_efficiency_report`

**Response includes:**
- Overall efficiency score (0-100)
- Per-tier efficiency analysis
- Actionable optimization suggestions
- Potential monthly savings estimation
- Tier utilization analysis

---

## Export Tools

### mcp_mrkrabs_export_csv

Export cost data to CSV file.

**Endpoint:** `POST /tools/mcp_mrkrabs_export_csv`

**Request Schema:**
```json
{
  "period_days": "number (7-90)",
  "output_dir": "string",
  "output_file": "string"
}
```

**Response:**
```json
{
  "success": true,
  "file_path": "/tmp/cost_report_2026-05-07.csv",
  "records_exported": 156,
  "period": "30 days"
}
```

**CSV Columns:**
- timestamp
- session_id
- tier (L0/L1/L2/L3)
- model
- input_tokens
- output_tokens
- cost_usd
- success
- duration_seconds

---

### mcp_mrkrabs_export_json

Export cost data as JSON (in-memory, no file I/O).

**Endpoint:** `POST /tools/mcp_mrkrabs_export_json`

**Request Schema:**
```json
{
  "period_days": "number (7-90)"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "metadata": {...},
    "records": [...]
  }
}
```

---

## API Reference

### Health & Info Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service information |
| GET | `/health` | Health check |
| GET | `/tools` | List all available tools |
| GET | `/openapi.json` | OpenAPI schema |

### Session Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/mcp_mrkrabs_session_init` | Create new session |
| GET | `/tools/mcp_mrkrabs_session_status/{id}` | Get session status |
| DELETE | `/tools/mcp_mrkrabs_session_close/{id}` | Close session |
| POST | `/tools/mcp_mrkrabs_ping` | Health check with optional session |

### Cost Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/mcp_mrkrabs_cost_estimate` | Estimate LLM call cost |
| POST | `/tools/mcp_mrkrabs_budget_check` | Check if within budget |
| POST | `/tools/mcp_mrkrabs_cost_track` | Record actual spending |

### CrewAI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/mcp_mrkrabs_crew_create` | Create multi-agent crew |
| POST | `/tools/mcp_mrkrabs_crew_execute` | Execute crew |
| POST | `/tools/mcp_mrkrabs_agent_execute` | Execute single agent task |

### Analytics Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/mcp_mrkrabs_analytics_summary` | Get cost analytics |
| POST | `/tools/mcp_mrkrabs_cost_trend` | Get daily trend analysis |
| POST | `/tools/mcp_mrkrabs_efficiency_report` | Get efficiency metrics |

### Export Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/mcp_mrkrabs_export_csv` | Export to CSV file |
| POST | `/tools/mcp_mrkrabs_export_json` | Export to JSON |

---

## Examples

### Complete Workflow: Research Task with Budget Control

```bash
# 1. Initialize session with $5 budget
SESSION_RESPONSE=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '''{"budget_limit": 5.0, "enforcement_mode": "notify_then_fail"}''')

SESSION_ID=$(echo $SESSION_RESPONSE | jq -r '.session_id')
echo "Session ID: $SESSION_ID"

# 2. Estimate cost for a task
ESTIMATE=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"model\": \"google/gemma-7b-it\", \"input_tokens\": 500}")

echo "Estimated cost: $(echo $ESTIMATE | jq .estimated_cost)"

# 3. Check budget
BUDGET_CHECK=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_budget_check \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"would_spend\": 0.5}")

CAN_PROCEED=$(echo $BUDGET_CHECK | jq -r '.can_proceed')

if [ "$CAN_PROCEED" = "true" ]; then
  echo "Budget OK, proceeding..."
  
  # 4. Execute crew task
  CREW_RESPONSE=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_execute \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"crew_id\": \"research-crew\", \"task\": \"Research quantum computing basics\"}")
  
  echo "Crew execution result: $CREW_RESPONSE"
fi

# 5. Get analytics summary
ANALYTICS=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_analytics_summary \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\"}")

echo "Analytics: $ANALYTICS"

# 6. Close session
curl -X DELETE http://localhost:8000/tools/mcp_mrkrabs_session_close/$SESSION_ID
```

---

## Troubleshooting

### Common Issues

#### Issue: Server won't start on port 8000

**Error:** `Address already in use`

**Solution:** Either kill the existing process or change port:
```bash
export MCP_PORT=9000
python -m src.mcp.server
```

---

#### Issue: Session expires too quickly

**Symptom:** `Session not found` errors after a few minutes

**Solution:** Increase session TTL:
```bash
export SESSION_TTL=7200  # 2 hours
```

---

#### Issue: Budget exceeded, tasks blocked

**Symptom:** `Budget limit exceeded` error

**Solutions:**
1. Check current spending:
   ```bash
   curl http://localhost:8000/tools/mcp_mrkrabs_session_status/{session_id}
   ```
2. Close and recreate session with higher budget
3. Use cheaper models (L0 tier) for simpler tasks

---

#### Issue: Authentication required but not configured

**Error:** `401 Unauthorized`

**Solution:** Either set API key or disable auth:
```bash
# Option 1: Set API key
export MCP_API_KEY="your-key"

# Option 2: Remove/unset the variable (default)
unset MCP_API_KEY
```

---

#### Issue: CrewAI not available

**Error:** `CrewAI module not found`

**Solution:** Install CrewAI:
```bash
pip install crewai
```

The server will gracefully degrade if CrewAI is unavailable.

---

### Error Codes Reference

| Code | Meaning | Solution |
|------|---------|----------|
| 200 | Success | - |
| 400 | Bad Request | Check JSON format and required fields |
| 401 | Unauthorized | Provide valid API key (if auth enabled) |
| 404 | Not Found | Check endpoint path and session_id |
| 429 | Rate Limit Exceeded | Wait and retry, or increase limits |
| 500 | Server Error | Check server logs for details |

---

### Getting Help

1. **Check Server Logs**: The server logs all requests with `structlog`
2. **Health Endpoint**: `curl http://localhost:8000/health` shows current session count
3. **Test Suite**: Run tests to verify installation:
   ```bash
   ./tests/run_mcp_tests.sh
   ```

---

## Appendix A: Model Tiers and Pricing

### Tier Configuration (Default)

| Tier | Models | Use Case | Cost Level |
|------|--------|----------|------------|
| L0 | `google/gemma-7b-it`, LM Studio local | Simple tasks, classification | Lowest |
| L1 | `meta-llama/llama-3-8b-instruct` | General purpose tasks | Low |
| L2 | `mistralai/mistral-7b-instruct` | Complex reasoning | Medium |
| L3 | `openai/gpt-4o`, `anthropic/claude-3-opus` | Critical, high-quality tasks | Highest |

### Custom Tier Configuration

You can customize tiers in your session initialization:
```json
{
  "budget_limit": 10.0,
  "default_tier": "L1",
  "models": [
    "your-preferred-model-1",
    "your-preferred-model-2"
  ]
}
```

---

## Appendix B: OpenAPI Schema

Full OpenAPI schema available at: `http://localhost:8000/openapi.json`

You can generate client code from this schema using tools like `openapi-generator` or view interactive documentation with Swagger UI.

---

**Document Version**: 1.0.0  
**Last Updated**: May 7, 2026  
**Maintained By**: MR-Krabs Development Team
