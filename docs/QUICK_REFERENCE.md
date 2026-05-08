# MR-Krabs MCP Server - Quick Reference

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: ✅ Production Ready

---

## 📚 Documentation Guide

| Document | Purpose | Lines |
|----------|---------|-------|
| **[MCP_USER_GUIDE.md](./MCP_USER_GUIDE.md)** | Complete user guide with setup, config, and workflows | 822 |
| **[MCP_TOOLS_REFERENCE.md](./MCP_TOOLS_REFERENCE.md)** | Detailed schema for all 16 MCP tools | 949 |
| **[MCP_USAGE_EXAMPLES.md](./MCP_USAGE_EXAMPLES.md)** | 6 practical examples (bash, Python, Docker) | 653 |
| **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** | Debugging guide with common issues | 490 |

---

## Quick Start (1-Minute Setup)

```bash
# 1. Start server
cd /home/sblanken/working/code/MR-Krabs
python -m src.mcp.server

# 2. Verify health
curl http://localhost:8000/health

# 3. Create session
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '{"budget_limit": 10.0}'

# 4. Execute task
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_agent_execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<your-session-id>",
    "agent_config": {"name": "assistant", "role": "Helper", "goal": "Assist users"},
    "task": "Explain quantum computing in one sentence"
  }'
```

---

## Available Tools (16 Total)

### Session Management (4 tools)
| Tool | Description |
|------|-------------|
| `mcp_mrkrabs_session_init` | Create new session with budget limit |
| `mcp_mrkrabs_session_status` | Get session status and stats |
| `mcp_mrkrabs_session_close` | Close session and finalize |
| `mcp_mrkrabs_ping` | Health check (optional session validation) |

### Cost Management (3 tools)
| Tool | Description |
|------|-------------|
| `mcp_mrkrabs_cost_estimate` | Estimate LLM call cost before execution |
| `mcp_mrkrabs_budget_check` | Check if expenditure fits budget |
| `mcp_mrkrabs_cost_track` | Record actual spending |

### CrewAI Integration (3 tools)
| Tool | Description |
|------|-------------|
| `mcp_mrkrabs_crew_create` | Create multi-agent crew |
| `mcp_mrkrabs_crew_execute` | Execute crew tasks |
| `mcp_mrkrabs_agent_execute` | Execute single agent task |

### Analytics & Reporting (3 tools)
| Tool | Description |
|------|-------------|
| `mcp_mrkrabs_analytics_summary` | Get cost and performance analytics |
| `mcp_mrkrabs_cost_trend` | Daily trend analysis with ASCII chart |
| `mcp_mrkrabs_efficiency_report` | Efficiency metrics + optimization tips |

### Export Tools (2 tools)
| Tool | Description |
|------|-------------|
| `mcp_mrkrabs_export_csv` | Export to CSV file |
| `mcp_mrkrabs_export_json` | Export as JSON (in-memory) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8000` | Port number |
| `SESSION_TTL` | `3600` | Session TTL in seconds (1 hour) |
| `MCP_API_KEY` | *(none)* | Bearer token for auth (optional) |
| `VAULT_MASTER_KEY_FILE` | `~/.mrkrabs/master.key` | Vault encryption key path |

---

## Common Commands

### List All Tools
```bash
curl http://localhost:8000/tools | jq .
```

### Get Session Status
```bash
curl http://localhost:8000/tools/mcp_mrkrabs_session_status/<session_id>
```

### Close Session
```bash
curl -X DELETE http://localhost:8000/tools/mcp_mrkrabs_session_close/<session_id>
```

### Get Analytics (7 days)
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_analytics_summary \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq .
```

---

## Budget Enforcement Modes

| Mode | Behavior |
|------|----------|
| `notify_only` | Log warnings, always allow execution |
| `fail` | Block immediately when budget exceeded |
| `notify_then_fail` | Warn once, then block (recommended) |
| `fail_with_notification` | Block + send alert (future: webhook/Slack) |

---

## Tier Configuration (Default)

| Tier | Models | Cost Level | Use Case |
|------|--------|------------|----------|
| L0 | `google/gemma-7b-it`, LM Studio | Lowest | Simple tasks, classification |
| L1 | `meta-llama/llama-3-8b-instruct` | Low | General purpose |
| L2 | `mistralai/mistral-7b-instruct` | Medium | Complex reasoning |
| L3 | `openai/gpt-4o`, Claude Opus | Highest | Critical, high-quality tasks |

---

## Error Codes

| Code | HTTP | Cause | Solution |
|------|------|-------|----------|
| `INVALID_REQUEST` | 400 | Bad JSON/missing fields | Check schema |
| `SESSION_NOT_FOUND` | 404 | Invalid/expired session ID | Create new session |
| `BUDGET_EXCEEDED` | 400 | Budget limit hit | Increase budget or reduce scope |
| `AUTHENTICATION_REQUIRED` | 401 | API key missing | Set `Authorization` header |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests | Slow down, retry later |
| `INTERNAL_ERROR` | 500 | Server error | Check logs |

---

## Project Status

### ✅ Complete (Phase 1)
- [x] Session management with TTL
- [x] Cost estimation and tracking
- [x] Budget enforcement (4 modes)
- [x] CrewAI integration (stateful/stateless)
- [x] Analytics (summary, trends, efficiency)
- [x] CSV/JSON export
- [x] Vault security (Fernet encryption)
- [x] 112 tests passing
- [x] Full documentation (this suite)

### 📋 Next Priorities
- [ ] Auth middleware enhancement
- [ ] Deployment scripts (Docker, k8s)
- [ ] Webhook notifications for budget alerts
- [ ] Prometheus metrics export
- [ ] Rate limiting per client

---

## Testing

```bash
# Run all MCP tests
./tests/run_mcp_tests.sh

# Run specific test file
pytest tests/mcp/test_server.py -v

# Run analytics tests only
pytest tests/mcp/test_analytics_tools.py -v
```

### Test Coverage
| Module | Coverage |
|--------|----------|
| `server.py` | 74% |
| `analytics_tools.py` | 91% |
| `cost_tools.py` | 99% |
| **Overall** | **~85%** |

---

## Links

- **Project Root**: `/home/sblanken/working/code/MR-Krabs`
- **Main README**: `README.md`
- **Architecture**: `docs/MCP_ARCHITECTURE.md`
- **Implementation Plan**: `docs/MCP_SERVER_IMPLEMENTATION_PLAN.md`
- **Testing Guide**: `docs/MCP_TESTING_INFRASTRUCTURE.md`

---

**Last Updated**: May 7, 2026  
**Document Count**: 4 comprehensive guides (2,914 lines total)
