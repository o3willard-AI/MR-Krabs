# MR-Krabs MCP Server - Troubleshooting Guide

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: Production Ready

---

## Quick Diagnostics

### Health Check

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

If this fails, the server is not running. Start it with:
```bash
cd /home/sblanken/working/code/MR-Krabs
python -m src.mcp.server
```

---

### List Available Tools

```bash
curl http://localhost:8000/tools | jq .
```

This should return all 16 MCP tools organized by category.

---

## Common Issues & Solutions

### Issue 1: Port Already in Use

**Error Message**:
```
OSError: [Errno 98] Address already in use
```

**Cause**: Another process is using port 8000 (default).

**Solutions**:

**Option A - Kill Existing Process**:
```bash
# Find the process
lsof -i :8000

# Kill it
kill -9 <PID>
```

**Option B - Use Different Port**:
```bash
export MCP_PORT=9000
python -m src.mcp.server
```

Then access at `http://localhost:9000`

---

### Issue 2: Module Import Errors

**Error Message**:
```
ModuleNotFoundError: No module named 'crewai'
```

**Cause**: Optional dependency not installed.

**Solution**:
```bash
pip install crewai
```

**Note**: The server gracefully degrades if CrewAI is unavailable. Core cost tracking and session management still work.

---

### Issue 3: Session Not Found Errors

**Error Message**:
```json
{
  "success": false,
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'sess_xxx' not found or expired"
  }
}
```

**Possible Causes & Solutions**:

1. **Session Expired** (Most Common)
   - Default TTL is 3600 seconds (1 hour)
   - Create a new session with `session_init`
   - Or increase TTL: `export SESSION_TTL=7200`

2. **Invalid Session ID**
   - Check for typos in the session_id
   - Session IDs are case-sensitive

3. **Session Was Closed**
   - Once closed, sessions cannot be reopened
   - Initialize a new session

---

### Issue 4: Budget Exceeded Errors

**Error Message**:
```json
{
  "success": false,
  "error": {
    "code": "BUDGET_EXCEEDED",
    "message": "Budget limit exceeded for session sess_xxx"
  }
}
```

**Solutions**:

1. **Check Current Spending**:
   ```bash
   curl http://localhost:8000/tools/mcp_mrkrabs_session_status/sess_xxx
   ```

2. **Create New Session with Higher Budget**:
   ```bash
   curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
     -H "Content-Type: application/json" \
     -d '{"budget_limit": 50.0}'
   ```

3. **Use Cheaper Tiers**: Switch from L2/L3 to L0/L1 for simpler tasks

4. **Change Enforcement Mode**: Use `notify_only` if you want warnings instead of hard blocks

---

### Issue 5: Authentication Required

**Error Message**:
```json
{
  "success": false,
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "API key required but not provided"
  }
}
```

**Solutions**:

**Option A - Provide API Key**:
```bash
curl http://localhost:8000/tools \
  -H "Authorization: Bearer your-api-key"
```

**Option B - Disable Auth** (if running locally):
```bash
unset MCP_API_KEY
# Restart server
python -m src.mcp.server
```

---

### Issue 6: Vault Not Initialized

**Error Message**:
```
FileNotFoundError: Master key file not found at ~/.mrkrabs/master.key
```

**Solution**: Initialize the vault:
```bash
cd /home/sblanken/working/code/MR-Krabs
./scripts/setup-vault.sh init
```

Then add your API keys:
```bash
./scripts/setup-vault.sh add-key openai sk-***...
./scripts/setup-vault.sh add-key anthropic your-key-here
```

---

### Issue 7: Rate Limiting Errors

**Error Message**:
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded for provider openai"
  }
}
```

**Cause**: Default rate limit is 10 requests/second per provider.

**Solutions**:

1. **Slow Down Your Requests**: Add delays between calls
2. **Increase Rate Limit**: Modify `src/core/vault.py` RateLimiter settings (advanced)
3. **Use Different Provider**: Spread load across multiple providers

---

### Issue 8: CrewAI Execution Fails

**Error Message**:
```
crewai.exceptions.CrewException: Task execution failed after 3 retries
```

**Troubleshooting Steps**:

1. **Check Task Complexity**: Simplify the task description
2. **Increase Budget**: Crew tasks may need higher budgets for escalation
3. **Use Appropriate Tier**: Complex tasks may need L2 or L3 tiers
4. **Enable Verbose Logging**: Add `"verbose": true` to crew_config to see what's happening

**Example Debug Request**:
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_crew_create \
  -H "Content-Type: application/json" \
  -d '{
    "crew_config": {
      "agents": [{"name": "test", "role": "tester", "goal": "Test task"}],
      "tasks": [{"description": "Simple test task", "agent_name": "test"}],
      "verbose": true
    }
  }'
```

---

### Issue 9: CSV/JSON Export Fails

**Error Message**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Period must be between 7 and 90 days"
  }
}
```

**Solution**: Use valid period range:
```bash
# Valid (7 to 90 days)
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_csv \
  -H "Content-Type: application/json" \
  -d '{"period_days": 30}'  # ✓ Valid

# Invalid
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_csv \
  -H "Content-Type: application/json" \
  -d '{"period_days": 5}'   # ✗ Too short
```

---

### Issue 10: Memory Errors on Large Exports

**Error Message**:
```
MemoryError: Unable to allocate large array
```

**Cause**: Exporting too much data at once.

**Solutions**:

1. **Reduce Period Days**: Use smaller time ranges
2. **Use CSV Instead of JSON**: CSV is more memory-efficient for large datasets
3. **Add Session Filter**: Filter to specific sessions
   ```json
   {"period_days": 90, "session_id": "sess_abc123"}
   ```

---

## Debugging Techniques

### Enable Verbose Logging

Set environment variable before starting server:
```bash
export STRUCTLOG_LEVEL=debug
python -m src.mcp.server
```

Or use Python logging:
```bash
export PYTHONFAULTHANDLER=1
export RUST_BACKTRACE=1
python -m src.mcp.server
```

---

### Check Server Logs

Logs are written to stdout by default. For production, redirect to file:
```bash
python -m src.mcp.server > mrkrabs.log 2>&1 &
```

Then monitor:
```bash
tail -f mrkrabs.log
```

---

### Inspect Session State

All sessions are stored in memory. Use the status endpoint:
```bash
# List all sessions (check health endpoint)
curl http://localhost:8000/health | jq .session_count

# Get specific session details
curl http://localhost:8000/tools/mcp_mrkrabs_session_status/sess_xxx
```

---

### Test with Real LLM Calls

To test with actual API calls (costs money!):

1. **Initialize Vault**:
   ```bash
   ./scripts/setup-vault.sh init
   ./scripts/setup-vault.sh add-key openrouter your-api-key
   ```

2. **Create Session with Real Budget**:
   ```bash
   curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
     -H "Content-Type: application/json" \
     -d '{"budget_limit": 1.0}'
   ```

3. **Execute Simple Task**:
   ```bash
   curl -X POST http://localhost:8000/tools/mcp_mrkrabs_agent_execute \
     -H "Content-Type: application/json" \
     -d '{
       "session_id": "sess_xxx",
       "agent_config": {"name": "test", "role": "tester", "goal": "Test"},
       "task": "Say hello in one word"
     }'
   ```

---

## Performance Issues

### Slow Response Times

**Symptoms**: Requests taking >5 seconds to respond.

**Possible Causes**:

1. **Network Latency**: Check connection to LLM provider
2. **Complex Tasks**: Crew tasks with multiple agents take longer
3. **Server Overloaded**: Check CPU/memory usage
4. **Large Exports**: CSV/JSON for long periods is slow

**Solutions**:

- Use cheaper, faster models (L0 tier)
- Reduce crew complexity
- Monitor server resources: `htop` or `top`
- Cache frequently-used data

---

### High Memory Usage

**Symptoms**: Server using >1GB RAM.

**Cause**: Sessions and cost tracking data accumulate in memory.

**Solutions**:

1. **Close Unused Sessions**: Regularly call `session_close`
2. **Reduce SESSION_TTL**: Default is 3600s, try 1800s or 900s
3. **Restart Server Periodically**: Clear all in-memory state
4. **Use Export Tools**: Download data and clear tracking (future feature)

---

## Error Codes Reference

| Code | HTTP Status | Category | User Action Required? |
|------|-------------|----------|----------------------|
| `INVALID_REQUEST` | 400 | Input Validation | Yes - fix request format |
| `SESSION_NOT_FOUND` | 404 | Session Management | Yes - create new session |
| `SESSION_EXPIRED` | 410 | Session Management | Yes - create new session |
| `BUDGET_EXCEEDED` | 400 | Budget Enforcement | Yes - increase budget or reduce scope |
| `AUTHENTICATION_REQUIRED` | 401 | Authentication | Yes - provide API key |
| `INVALID_CREDENTIALS` | 401 | Authentication | Yes - check API key |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate Limiting | Wait, then retry |
| `CREWAI_NOT_AVAILABLE` | 503 | Dependency Missing | Install crewai or use alternative tools |
| `INTERNAL_ERROR` | 500 | Server Error | No - contact maintainer |
| `VAULT_NOT_INITIALIZED` | 500 | Vault Setup | Yes - run setup-vault.sh init |

---

## Getting Help

### Step-by-Step Debugging Checklist

1. ✅ Is the server running? (`curl http://localhost:8000/health`)
2. ✅ Are you using the correct port? (Check `MCP_PORT` env var)
3. ✅ Is your JSON valid? (Use `jq .` to validate requests)
4. ✅ Do required fields exist? (Check tool reference documentation)
5. ✅ Is your session still valid? (`session_status` endpoint)
6. ✅ Is your budget sufficient? (`budget_check` endpoint)
7. ✅ Are you providing auth if required? (Check `MCP_API_KEY`)

### Still Stuck?

1. **Check Server Logs**: Look for stack traces or error messages
2. **Run Test Suite**: Verify installation is working
   ```bash
   ./tests/run_mcp_tests.sh
   ```
3. **Reinstall Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Check GitHub Issues**: See if others have reported the same problem
5. **Contact Maintainers**: With logs and reproduction steps

---

## FAQ

**Q: How do I reset all sessions?**  
A: Restart the server or use `session_close` on each session individually.

**Q: Can I pause a session?**  
A: No, but you can close it and create a new one with the same budget later.

**Q: How much does it cost to run the MCP server itself?**  
A: The server is free to run - you only pay for actual LLM API calls.

**Q: Can I use local models only?**  
A: Yes! Configure LM Studio or other local inference servers and set them as your default providers.

**Q: How do I monitor costs in real-time?**  
A: Use the `session_status` endpoint periodically to check current spending.

**Q: What happens when a session times out?**  
A: The session is automatically cleaned up, and further requests with that ID will fail with SESSION_EXPIRED.

---

**Last Updated**: May 7, 2026  
**Maintainer Contact**: Check project README for support channels
