# MR-Krabs MCP Server - Tool Reference Documentation

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: Production Ready

This document provides complete schema definitions for all MCP tools exposed by the MR-Krabs server.

---

## Tool Categories

| Category | Count | Purpose |
|----------|-------|---------|
| **Session Management** | 4 | Create, monitor, and close sessions |
| **Cost Management** | 3 | Estimate, check, and track costs |
| **CrewAI Integration** | 3 | Multi-agent workflow orchestration |
| **Analytics & Reporting** | 3 | Cost analysis and efficiency metrics |
| **Export Tools** | 2 | CSV/JSON data export |
| **Utility** | 1 | Health checks and ping |

**Total Tools**: 16

---

## Session Management Tools

### mcp_mrkrabs_session_init

Create a new cost-tracking session with configurable budget limits.

**Endpoint**: `POST /tools/mcp_mrkrabs_session_init`

#### Request Schema

```json
{
  "budget_limit": {
    "type": "number",
    "description": "Maximum budget in USD for this session",
    "default": 10.0,
    "minimum": 0.01
  },
  "enforcement_mode": {
    "type": "string",
    "enum": ["notify_only", "fail", "notify_then_fail", "fail_with_notification"],
    "default": "notify_then_fail",
    "description": "How to handle budget limits"
  },
  "warning_threshold": {
    "type": "number",
    "description": "Percentage of budget at which to warn (0-100)",
    "default": 80.0,
    "minimum": 0,
    "maximum": 100
  },
  "default_tier": {
    "type": "string",
    "enum": ["L0", "L1", "L2", "L3"],
    "default": "L0",
    "description": "Default tier for task execution"
  },
  "models": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Preferred models for this session (optional)",
    "examples": [
      ["google/gemma-7b-it", "meta-llama/llama-3-8b-instruct"]
    ]
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "session_id": "sess_abc123def456",
  "status": "active",
  "config": {
    "budget_limit": 10.0,
    "enforcement_mode": "notify_then_fail",
    "warning_threshold": 80.0,
    "default_tier": "L0"
  },
  "created_at": "2026-05-07T12:34:56Z"
}
```

#### Enforcement Mode Details

| Mode | Behavior | Warning Count |
|------|----------|---------------|
| `notify_only` | Always allows execution, logs warnings when budget exceeded | Unlimited |
| `fail` | Immediately blocks when budget would be exceeded | 0 |
| `notify_then_fail` | Warns once, then blocks on subsequent attempts | 1 before blocking |
| `fail_with_notification` | Blocks + sends alert (webhook/Slack integration) | 0 |

---

### mcp_mrkrabs_session_status

Get current status and statistics for a session.

**Endpoint**: `GET /tools/mcp_mrkrabs_session_status/{session_id}`

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | The session identifier from `session_init` response |

#### Response Schema

```json
{
  "active": true,
  "session_id": "sess_abc123def456",
  "time_remaining_seconds": 3456,
  "budget_spent": 5.23,
  "budget_limit": 10.0,
  "budget_remaining": 4.77,
  "enforcement_mode": "notify_then_fail",
  "task_count": 12,
  "success_rate": 91.67,
  "created_at": "2026-05-07T12:34:56Z"
}
```

#### Response for Expired/Invalid Session

```json
{
  "active": false,
  "session_id": "invalid-session-id",
  "error": "Session not found or expired",
  "time_remaining_seconds": 0
}
```

---

### mcp_mrkrabs_session_close

Manually close a session and finalize statistics.

**Endpoint**: `DELETE /tools/mcp_mrkrabs_session_close/{session_id}`

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | The session identifier to close |

#### Response Schema

```json
{
  "closed": true,
  "session_id": "sess_abc123def456",
  "final_spending": 8.47,
  "total_tasks": 18,
  "success_rate": 94.44,
  "closed_at": "2026-05-07T14:23:11Z"
}
```

---

### mcp_mrkrabs_ping

Health check with optional session validation.

**Endpoint**: `POST /tools/mcp_mrkrabs_ping`

#### Request Schema (Optional)

```json
{
  "session_id": "sess_abc123def456"  // Optional: validate specific session
}
```

#### Response Schema (No Session)

```json
{
  "status": "ok",
  "service": "mr-krabs-mcp",
  "timestamp": "2026-05-07T12:34:56Z"
}
```

#### Response Schema (With Session)

```json
{
  "status": "ok",
  "service": "mr-krabs-mcp",
  "session_active": true,
  "session_id": "sess_abc123def456",
  "remaining_budget": 4.77,
  "timestamp": "2026-05-07T12:34:56Z"
}
```

---

## Cost Management Tools

### mcp_mrkrabs_cost_estimate

Estimate the cost of an LLM call before execution.

**Endpoint**: `POST /tools/mcp_mrkrabs_cost_estimate`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Session to associate with this estimate (optional)",
    "required": false
  },
  "model": {
    "type": "string",
    "description": "Model identifier for cost estimation",
    "required": true,
    "examples": [
      "google/gemma-7b-it",
      "meta-llama/llama-3-8b-instruct",
      "openai/gpt-4o"
    ]
  },
  "input_tokens": {
    "type": "integer",
    "description": "Estimated input token count (if known)",
    "required": false,
    "oneOf": [
      {"required": ["input_tokens"]},
      {"required": ["prompt_text"]}
    ]
  },
  "output_tokens": {
    "type": "integer",
    "description": "Estimated output token count (if known)",
    "required": false,
    "default": 100
  },
  "prompt_text": {
    "type": "string",
    "description": "Actual prompt text (token count will be estimated)",
    "required": false
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "estimated_cost": 0.025,
  "model": "google/gemma-7b-it",
  "input_tokens": 1000,
  "output_tokens": 500,
  "pricing": {
    "input_price_per_1k": 0.02,
    "output_price_per_1k": 0.02,
    "currency": "USD"
  }
}
```

#### Supported Models (Partial List)

| Model | Input Price | Output Price | Notes |
|-------|-------------|--------------|-------|
| `google/gemma-7b-it` | $0.02/1k | $0.02/1k | L0 tier, cheapest |
| `meta-llama/llama-3-8b-instruct` | $0.05/1k | $0.05/1k | L1 tier |
| `mistralai/mistral-7b-instruct` | $0.20/1k | $0.20/1k | L2 tier |
| `openai/gpt-4o` | $5.00/1k | $15.00/1k | L3 tier, most expensive |

---

### mcp_mrkrabs_budget_check

Check if a proposed expenditure fits within the session budget.

**Endpoint**: `POST /tools/mcp_mrkrabs_budget_check`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Session to check budget against",
    "required": true
  },
  "would_spend": {
    "type": "number",
    "description": "Proposed expenditure amount in USD",
    "required": true,
    "minimum": 0.01
  }
}
```

#### Response Schema (Can Proceed)

```json
{
  "success": true,
  "can_proceed": true,
  "remaining_budget": 18.50,
  "budget_limit": 25.0,
  "already_spent": 6.50,
  "would_spend": 0.75,
  "would_be_at_percentage": 31.0,
  "warning": null
}
```

#### Response Schema (Would Exceed)

```json
{
  "success": true,
  "can_proceed": false,
  "remaining_budget": 0.50,
  "budget_limit": 10.0,
  "already_spent": 9.50,
  "would_spend": 2.00,
  "would_exceed_by": 1.50,
  "enforcement_mode": "notify_then_fail",
  "warning": "Budget would be exceeded by $1.50"
}
```

---

### mcp_mrkrabs_cost_track

Record actual spending against a session.

**Endpoint**: `POST /tools/mcp_mrkrabs_cost_track`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Session to record cost against",
    "required": true
  },
  "amount": {
    "type": "number",
    "description": "Actual cost incurred in USD",
    "required": true,
    "minimum": 0.01
  },
  "model": {
    "type": "string",
    "description": "Model used for this task (for analytics)",
    "required": false
  },
  "description": {
    "type": "string",
    "description": "Description of what was accomplished",
    "required": false
  },
  "task_id": {
    "type": "string",
    "description": "Unique identifier for this task",
    "required": false
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "amount_recorded": 0.47,
  "session_id": "sess_abc123",
  "new_total_spent": 5.70,
  "budget_remaining": 4.30,
  "warning_triggered": false
}
```

---

## CrewAI Integration Tools

### mcp_mrkrabs_crew_create

Create a multi-agent crew configuration for cost-optimized execution.

**Endpoint**: `POST /tools/mcp_mrkrabs_crew_create`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Session to associate with this crew (optional)",
    "required": false
  },
  "crew_config": {
    "type": "object",
    "required": true,
    "properties": {
      "agents": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["name", "role", "goal"],
          "properties": {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "goal": {"type": "string"},
            "backstory": {"type": "string"}
          }
        },
        "minItems": 1,
        "description": "List of agents in the crew"
      },
      "tasks": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["description", "agent_name"],
          "properties": {
            "description": {"type": "string"},
            "expected_output": {"type": "string"},
            "agent_name": {"type": "string"}
          }
        },
        "minItems": 1,
        "description": "List of tasks to execute"
      },
      "verbose": {
        "type": "boolean",
        "default": false,
        "description": "Enable verbose logging"
      }
    }
  }
}
```

#### Example Request

```json
{
  "session_id": "sess_abc123",
  "crew_config": {
    "agents": [
      {
        "name": "researcher",
        "role": "Research Analyst",
        "goal": "Gather accurate information from reliable sources",
        "backstory": "You are an expert researcher with access to multiple knowledge bases."
      },
      {
        "name": "writer",
        "role": "Content Writer",
        "goal": "Create well-structured, engaging content",
        "backstory": "You are a professional writer with experience in technical documentation."
      }
    ],
    "tasks": [
      {
        "description": "Research the history of artificial intelligence from 1950 to present",
        "agent_name": "researcher",
        "expected_output": "A comprehensive timeline of AI development milestones"
      },
      {
        "description": "Write a 1000-word article summarizing AI history for a general audience",
        "agent_name": "writer",
        "expected_output": "An engaging article suitable for publication"
      }
    ],
    "verbose": true
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "crew_id": "crew_xyz789abc",
  "agents_count": 2,
  "tasks_count": 2,
  "estimated_cost_range": {
    "min": 0.50,
    "max": 2.00
  },
  "created_at": "2026-05-07T12:34:56Z"
}
```

---

### mcp_mrkrabs_crew_execute

Execute a previously created crew or run tasks inline.

**Endpoint**: `POST /tools/mcp_mrkrabs_crew_execute`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Session for execution (optional if crew has default)",
    "required": false
  },
  "crew_id": {
    "type": "string",
    "description": "ID of crew to execute (from crew_create response)",
    "required": true
  },
  "task_override": {
    "type": "string",
    "description": "Optional task override that replaces all predefined tasks",
    "required": false
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "crew_id": "crew_xyz789abc",
  "execution_id": "exec_123456789",
  "status": "completed",
  "results": {
    "task_1": "AI began with the Dartmouth Summer Research Project in 1956...",
    "task_2": "# The Evolution of Artificial Intelligence

Artificial intelligence has..."
  },
  "cost_breakdown": {
    "total_cost": 1.23,
    "tasks_completed": 2,
    "escalations_used": 0
  },
  "execution_time_seconds": 45.6
}
```

---

### mcp_mrkrabs_agent_execute

Execute a single agent task without full crew setup.

**Endpoint**: `POST /tools/mcp_mrkrabs_agent_execute`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "required": false
  },
  "agent_config": {
    "type": "object",
    "required": true,
    "properties": {
      "name": {"type": "string"},
      "role": {"type": "string"},
      "goal": {"type": "string"},
      "backstory": {"type": "string"}
    }
  },
  "task": {
    "type": "string",
    "description": "The task to execute",
    "required": true
  },
  "model_override": {
    "type": "string",
    "description": "Override the default model selection",
    "required": false
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "execution_id": "exec_987654321",
  "result": "The task has been completed successfully...",
  "cost": 0.35,
  "tier_used": "L0",
  "model_used": "google/gemma-7b-it",
  "execution_time_seconds": 12.3
}
```

---

## Analytics & Reporting Tools

### mcp_mrkrabs_analytics_summary

Get comprehensive cost and performance analytics for a period.

**Endpoint**: `POST /tools/mcp_mrkrabs_analytics_summary`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "description": "Filter to specific session (optional)",
    "required": false
  },
  "period_days": {
    "type": "integer",
    "description": "Number of days to analyze (default: 7, range: 1-90)",
    "default": 7,
    "minimum": 1,
    "maximum": 90
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "data": {
    "period": "7 days",
    "total_spent": 45.67,
    "total_tasks": 128,
    "avg_cost_per_task": 0.357,
    "tier_breakdown": {
      "L0": {"tasks": 82, "cost": 8.20, "percentage": 64.06},
      "L1": {"tasks": 32, "cost": 24.60, "percentage": 25.00},
      "L2": {"tasks": 12, "cost": 9.80, "percentage": 9.38},
      "L3": {"tasks": 2, "cost": 3.07, "percentage": 1.56}
    },
    "success_rate": 94.5,
    "escalation_rate": 21.1,
    "most_used_models": [
      {"model": "google/gemma-7b-it", "count": 82},
      {"model": "meta-llama/llama-3-8b-instruct", "count": 32}
    ]
  }
}
```

---

### mcp_mrkrabs_cost_trend

Get daily cost trend analysis with ASCII visualization.

**Endpoint**: `POST /tools/mcp_mrkrabs_cost_trend`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "required": false
  },
  "period_days": {
    "type": "integer",
    "default": 7,
    "minimum": 1,
    "maximum": 90
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "data": {
    "period_days": 7,
    "daily_costs": [
      {"date": "2026-05-01", "cost": 2.34},
      {"date": "2026-05-02", "cost": 3.12},
      {"date": "2026-05-03", "cost": 1.87}
    ],
    "trend": "increasing",
    "percentage_change": 23.4,
    "min_daily_cost": 1.23,
    "max_daily_cost": 4.56,
    "avg_daily_cost": 2.67,
    "ascii_chart": "$4.00 │     █      
$3.00 │  █  █   █  
$2.00 │█  █ █ █ █  
$1.00 │█ █ █ █ █ █ 
      └──28 29 30  1  2  3  4"
  }
}
```

---

### mcp_mrkrabs_efficiency_report

Get efficiency metrics and optimization suggestions.

**Endpoint**: `POST /tools/mcp_mrkrabs_efficiency_report`

#### Request Schema

```json
{
  "session_id": {
    "type": "string",
    "required": false
  },
  "period_days": {
    "type": "integer",
    "default": 7,
    "minimum": 1,
    "maximum": 90
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "data": {
    "period": "7 days",
    "overall_efficiency_score": 85,
    "tier_analysis": {
      "L0": {
        "efficiency_score": 92,
        "task_count": 47,
        "avg_cost_per_task": 0.040,
        "success_rate": 98.5,
        "status": "Excellent ✅"
      },
      "L1": {
        "efficiency_score": 85,
        "task_count": 26,
        "avg_cost_per_task": 0.217,
        "success_rate": 96.0,
        "status": "Good 👍"
      }
    },
    "optimization_suggestions": [
      "Shift 3 L2 tasks to L1 for simpler operations (potential savings: $0.06/month)",
      "L0 tier performing excellently (score: 92) - consider routing more simple tasks to L0",
      "Current tier usage is optimized. No major changes needed."
    ],
    "potential_monthly_savings": 15.75,
    "utilization_analysis": {
      "total_tasks_analyzed": 85,
      "tier_utilization": {"L0": 55.3, "L1": 30.6, "L2": 11.8, "L3": 2.4},
      "recommendation": "Excellent tier distribution - maintaining optimal balance"
    }
  }
}
```

---

## Export Tools

### mcp_mrkrabs_export_csv

Export cost data to CSV file.

**Endpoint**: `POST /tools/mcp_mrkrabs_export_csv`

#### Request Schema

```json
{
  "period_days": {
    "type": "integer",
    "description": "Number of days of data to export (7-90)",
    "default": 30,
    "minimum": 7,
    "maximum": 90
  },
  "output_dir": {
    "type": "string",
    "description": "Directory path for output file",
    "default": "/tmp"
  },
  "output_file": {
    "type": "string",
    "description": "Filename for the CSV export",
    "default": "mrkrabs_cost_report.csv"
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "file_path": "/tmp/mrkrabs_cost_report_2026-05-07.csv",
  "records_exported": 156,
  "period": "30 days",
  "total_cost_exported": 87.34,
  "export_timestamp": "2026-05-07T15:30:00Z"
}
```

#### CSV Format

The exported CSV includes the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | When the task was executed (ISO 8601) |
| `session_id` | string | Session identifier |
| `task_id` | string | Unique task identifier |
| `tier` | string | Tier used (L0/L1/L2/L3) |
| `model` | string | Model used for execution |
| `input_tokens` | integer | Input token count |
| `output_tokens` | integer | Output token count |
| `cost_usd` | float | Cost in USD |
| `success` | boolean | Whether task succeeded |
| `duration_seconds` | float | Execution time |

---

### mcp_mrkrabs_export_json

Export cost data as JSON (in-memory, no file I/O).

**Endpoint**: `POST /tools/mcp_mrkrabs_export_json`

#### Request Schema

```json
{
  "period_days": {
    "type": "integer",
    "default": 30,
    "minimum": 7,
    "maximum": 90
  }
}
```

#### Response Schema

```json
{
  "success": true,
  "data": {
    "metadata": {
      "period_days": 30,
      "export_timestamp": "2026-05-07T15:30:00Z",
      "total_records": 156,
      "total_cost": 87.34
    },
    "records": [
      {
        "timestamp": "2026-05-07T10:15:30Z",
        "session_id": "sess_abc123",
        "task_id": "task_xyz789",
        "tier": "L0",
        "model": "google/gemma-7b-it",
        "input_tokens": 500,
        "output_tokens": 200,
        "cost_usd": 0.014,
        "success": true,
        "duration_seconds": 3.4
      }
    ]
  }
}
```

---

## Error Responses

All tools may return errors in the following format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {}  // Optional additional context
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Malformed request or missing required fields |
| `SESSION_NOT_FOUND` | 404 | Session ID does not exist or has expired |
| `BUDGET_EXCEEDED` | 400 | Requested action would exceed budget limit |
| `AUTHENTICATION_REQUIRED` | 401 | API key required but not provided |
| `INVALID_CREDENTIALS` | 401 | Provided API key is invalid |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests, slow down |
| `INTERNAL_ERROR` | 500 | Server-side error, check logs |

---

## Authentication (When Enabled)

If `MCP_API_KEY` environment variable is set, include the API key in requests:

```bash
curl http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"budget_limit": 10.0}'
```

---

**Document Version**: 1.0.0  
**Last Updated**: May 7, 2026
