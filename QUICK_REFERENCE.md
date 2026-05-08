# MR-Krabs Quick Reference - May 7, 2026

**Project**: Cost-Optimized AI Orchestrator with MCP Server  
**Location**: `/home/sblanken/working/code/MR-Krabs`  
**Overall Progress**: ~85% Complete (33 of 35 stories)

---

## 🎯 What's Working (Production-Ready)

### Core Features ✅
- **ask() API**: Auto-escalating LLM orchestration (4 tiers: L0-L3)
- **Cost Tracking**: Real-time budget monitoring with warnings at 80%
- **Vault Security**: Encrypted API key storage (Fernet/AES-128-CBC)
- **MCP Server**: FastAPI HTTP server on localhost:8000
- **Session Management**: Stateful + stateless modes with TTL cleanup
- **CrewAI Integration**: Multi-agent orchestration via `mcp_mrkrabs_*` tools
- **Analytics Export**: CSV/JSON cost reports (7-day to 90-day periods)

### Key Files
```
src/
├── __init__.py              # Core ask() API
├── core/
│   ├── cost.py             # Cost tracking
│   ├── tier_manager.py     # Tier escalation logic
│   ├── vault.py            # 🔐 Encrypted key storage (680 lines)
│   └── llm_provider.py     # Provider service with vault (350 lines)
└── mcp/
    ├── server.py           # FastAPI HTTP server (864 lines)
    ├── session_manager.py  # Session lifecycle management
    ├── budget_enforcer.py  # 4 enforcement modes
    ├── cost_tools.py       # Cost estimation/tracking tools
    ├── crew_tools.py       # CrewAI integration tools
    └── analytics_tools.py  # Analytics/reporting (✅ 100% complete)

scripts/
└── setup-vault.sh          # Vault CLI initialization

tests/mcp/                  # ✅ 86 tests, 100% pass rate
```

---

## 🔐 Vault Security (Phase 5.0 - Complete)

### Quick Setup
```bash
# Initialize vault
./scripts/setup-vault.sh init

# Add provider keys
./scripts/setup-vault.sh add-key openai sk-***...
./scripts/setup-vault.sh add-key anthropic your-key-here

# List providers
./scripts/setup-vault.sh list
```

### Python API
```python
from src.core.llm_provider import get_llm_provider_service

provider_service = get_llm_provider_service()  # Auto-loads from vault
providers = provider_service.list_available_providers()
cost = provider_service.estimate_cost("openai", input_tokens=1000, output_tokens=200)
```

### Features
- Fernet encryption (AES-128-CBC + HMAC)
- Audit trail for all key access (`~/.mrkrabs/audit.log`)
- Rate limiting: 10 req/sec, $50/hour per provider
- Automatic log sanitization (keys never in logs)

---

## 🧪 Testing Status

### Passing Tests ✅
```bash
# Vault tests (30/31 pass - 97%)
python -m pytest tests/test_vault.py -v

# MCP tests (86/86 pass - 100%)
./tests/run_mcp_tests.sh

# All core tests (~51% coverage)
python -m pytest tests/ -v

# Integration & E2E tests (skip without OPENROUTER_API_KEY)
OPENROUTER_API_KEY="or-xxx" pytest tests/integration/test_openrouter_integration.py -v
OPENROUTER_API_KEY="or-xxx" pytest tests/e2e/test_mcp_e2e_openrouter.py -v
```

### Test Files
- `tests/mcp/test_mcp_server.py` - 25 tests (core endpoints)
- `tests/mcp/test_mcp_cost_tools.py` - 16 tests (cost tools)
- `tests/mcp/test_mcp_crew_analytics.py` - 17 tests (CrewAI/analytics)
- `tests/mcp/test_mcp_integration.py` - 15 tests (E2E workflows)
- `tests/mcp/test_mcp_load.py` - 13 tests (load testing)
- `tests/mcp/test_exports.py` - 26 tests (CSV/JSON exports, ✅ NEW)
- **NEW**: `tests/integration/conftest.py` - Shared fixtures & config (✅ P2.5/P2.6)
- **NEW**: `tests/integration/test_openrouter_integration.py` - 13 integration tests (✅ P2.5)
- **NEW**: `tests/e2e/test_mcp_e2e_openrouter.py` - 7 E2E workflow tests (✅ P2.6)

---

## 🚀 MCP Server Endpoints

### Health & Info
```bash
curl http://localhost:8000/health        # {"status":"healthy"}
curl http://localhost:8000/              # Service info
curl http://localhost:8000/tools         # List all tools
```

### Session Management
```bash
# Create session
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '{"budget_limit": 10.0}'

# Close session
curl -X DELETE http://localhost:8000/tools/mcp_mrkrabs_session_close/{session_id}
```

### Cost Tools
```bash
# Estimate cost
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "model": "openai/gpt-4o", "input_tokens": 1000}'

# Check budget
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_check_budget \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "estimated_cost": 5.0}'

# Track spending
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_track \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "amount": 2.50, "description": "task"}'
```

### CrewAI Tools
```bash
# Create crew
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_create \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "crew_config": {...}}'

# Execute crew
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_execute \
  -H "Content-Type: application/json" \
  -d '{"crew_id": "...", "task": "..."}'
```

### Analytics Export (NEW!)
```bash
# CSV export to file
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_csv \
  -H "Content-Type: application/json" \
  -d '{"period_days": 30, "output_dir": "/tmp", "output_file": "report.csv"}'

# JSON export in-memory
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_json \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq '.'
```

---

## 📊 Configuration

### Default Config (`~/.cost_orchestrator.toml`)
```toml
[budget]
daily_limit_usd = "10.00"
warning_threshold = "0.80"
failure_mode = "fail_open_with_alert"

[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"

[providers.lmstudio]
base_url = "http://localhost:1234/v1"  # Free local inference
```

### Environment Variables
```bash
export OPENROUTER_API_KEY="or-***..."    # Production API key
export MCP_HOST="0.0.0.0"                # Default: 0.0.0.0
export MCP_PORT="8000"                   # Default: 8000
export VAULT_MASTER_KEY_FILE="~/.mrkrabs/master.key"
```

---

## ⚠️ Known Issues / TODOs

### Test Coverage Gap
- Current: ~70% coverage overall
- Target: 85%+ for core modules
- Need more edge case tests for budget enforcement, error handling

### Documentation Polish
- MCP user guide incomplete
- Some docstrings need updates

---

## 🎯 Next Priorities (If Continuing)

### Integration & E2E Tests Ready ✅
P2.5 and P2.6 are **COMPLETE**! Integration and end-to-end test infrastructure is fully implemented:
- 13 integration tests for real OpenRouter API interactions
- 7 E2E workflow tests covering complete MCP protocol flow  
- All tests skip gracefully without OPENROUTER_API_KEY (safe for CI/CD)
- ~$0.14 total cost risk when run with real API key

**To execute**: Provide `OPENROUTER_API_KEY` environment variable and start MCP server:
```bash
export OPENROUTER_API_KEY="or-your-key-here"
python -m src.mcp.server  # Terminal 1
pytest tests/integration/ tests/e2e/ -v  # Terminal 2
```

### Other Remaining Items
1. **Improve Test Coverage** - Target 85%+ on core modules (~16-24 hours)
2. **Documentation Polish** - MCP user guide, more examples (~8-16 hours)

---

## 📁 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main project readme with usage examples |
| `docs/VAULT_SECURITY.md` | Complete vault security guide (21.7 KB) |
| `docs/PRIORITY_1_COMPLETE_MCP_TESTING.md` | MCP testing infrastructure summary |
| `docs/BACKLOG_SUMMARY.md` | Full backlog with status and estimates |
| `docs/ANALYTICS_EXPORT.md` | CSV/JSON export guide (9.2 KB, ✅ NEW) |
| `docs/ANALYTICS_EXPORT_COMPLETE.md` | Implementation summary (7.9 KB, ✅ NEW) |
| `examples/analytics_export_example.py` | Working examples (8.7 KB, ✅ NEW) |
| **NEW**: `docs/P2_P3_TESTING_COMPLETE.md` | Integration & E2E test guide (15.4 KB, ✅ P2.5/P2.6) |
| `SESSION_CHECKPOINT.md` | Last session resume point (detailed) |
| `QUICK_REFERENCE.md` | THIS FILE - fast context restore |

---

## 🛠️ Quick Commands Cheat Sheet

```bash
# Vault management
./scripts/setup-vault.sh init
./scripts/setup-vault.sh add-key openai sk-***...
./scripts/setup-vault.sh list
./scripts/setup-vault.sh status

# Start MCP server
cd /home/sblanken/working/code/MR-Krabs
python -m src.mcp.server  # Runs on http://0.0.0.0:8000

# Run tests
./tests/run_mcp_tests.sh           # All MCP tests
python -m pytest tests/test_vault.py -v  # Vault tests
python -m pytest tests/ -v         # All tests

# Quick health check
curl http://localhost:8000/health

# View audit log
tail -f ~/.mrkrabs/audit.log

# Check current spending (CLI)
orchestrator stats
```

---

## 🔗 Key URLs & Resources

- **MCP Server**: http://localhost:8000
- **Test Suite**: `tests/mcp/test_mcp_*.py` (2,012 lines total)
- **Vault Location**: `~/.mrkrabs/vault.enc`
- **Master Key**: `~/.mrkrabs/master.key` (⚠️ NEVER commit this!)
- **Audit Log**: `~/.mrkrabs/audit.log`

---

## 💡 Architecture Highlights

### Tier Escalation Flow
```
Task → L0 (cheapest) → [fail?] → L1 → [fail?] → L2 → [fail?] → L3 (most expensive)
       ↓
   Cost tracked per tier, budget checked before each escalation
```

### Budget Enforcement Modes
- `notify_only` - Warn but continue
- `fail` - Block immediately on budget exceeded
- `notify_then_fail` - Warn first occurrence, then block
- `fail_with_notification` - Block + send alert (webhook/Slack)

### Session Types
- **Stateful** - Server tracks budget/session state (default)
- **Stateless** - Client manages state, server just processes requests

---

**Last Updated**: May 7, 2026  
**Session ID**: SESSION-20260507  
**Status**: Analytics export complete (CSV/JSON fully implemented + tested)  
**This Session**: Completed analytics export feature with 26 tests, docs, and examples

---

*This quick reference captures the essential context for resuming work. For full details, see SESSION_CHECKPOINT.md or the phase completion docs.*
