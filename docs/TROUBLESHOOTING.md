# Troubleshooting & FAQ

## Common Issues

### API Key Problems

#### "OPENROUTER_API_KEY not set"

**Cause**: Environment variable is not set.

**Fix:**
```bash
# Check if set
echo $OPENROUTER_API_KEY

# Set it (temporary for current session)
export OPENROUTER_API_KEY="sk-or-your-key-here"

# Set it permanently (add to ~/.bashrc or ~/.zshrc)
echo 'export OPENROUTER_API_KEY="sk-or-..."' >> ~/.bashrc
source ~/.bashrc
```

#### "Invalid API key"

**Cause**: API key is incorrect, expired, or has insufficient credits.

**Fix:**
1. Visit https://openrouter.ai/keys to verify/rotate your key
2. Check your OpenRouter account balance
3. Ensure the key hasn't been revoked

### Budget Issues

#### "Budget exceeded after finalization"

**Cause**: Task completed but cost exceeded budget limits.

**Fix:**
1. Run `orchestrator stats` to see current spending
2. Increase `daily_limit_usd` in config:
   ```toml
   [budget]
   daily_limit_usd = "20.00"
   ```
3. Break large tasks into smaller chunks
4. Use `fail_closed` mode to prevent overspending:
   ```toml
   failure_mode = "fail_closed"
   ```

#### "Budget reservation failed"

**Cause**: Estimated cost would exceed budget.

**Fix:**
- Reduce task complexity
- Increase budget in config
- Clear existing reservations by restarting your script

#### "Budget warning at 80%"

**Message:**
```
[BUDGET WARNING] $8.0000 / $10.00 (80.0%)
```

**This is informational only.** The task continues. To prevent warnings:
- Increase budget
- Reduce task frequency
- Accept warnings as early alerts

### Model Issues

#### "Model does not support tool calling"

**Cause**: The assigned model lacks tool/function calling capabilities.

**Fix:**
1. Check model capabilities:
   ```python
   from cost_orchestrator.model_capabilities import CapabilityChecker
   supports_tools = CapabilityChecker.supports_tool_calling(model_name)
   ```
2. Use a model with tool support:
   - claude-sonnet-4.6
   - grok-4.1-fast
   - llama-3.3-70b
3. Avoid using tools with L0 models for simple tasks

#### "Task keeps escalating to L3"

**Cause**: Tasks are too complex for cheaper models.

**Fix:**
1. Simplify task descriptions
2. Provide more context:
   ```python
   result = ask(
       "Fix this bug",
       context={
           "code": "...",
           "error_traceback": "...",
           "expected_behavior": "..."
       }
   )
   ```
3. Start at a higher tier manually:
   ```python
   result = ask("Complex task", tier="L2")
   ```
4. Use `orchestrator dry-run` to see escalation path

#### "Connection refused"

**Cause**: Cannot connect to LLM provider.

**Fix:**
```bash
# For OpenRouter (test connectivity)
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     https://openrouter.ai/api/v1/models

# For LM Studio
curl http://localhost:1234/v1/models

# Check firewall
sudo ufw status

# Restart LM Studio (if using)
lmstudio server
```

### Configuration Issues

#### "Config file not found"

**Fix:**
```bash
orchestrator init
```

#### "Invalid config format"

**Fix:**
```bash
# Validate TOML syntax
python -c "import tomllib; tomllib.load(open('.cost_orchestrator.toml', 'rb'))"

# Or use a TOML linter
# Re-run orchestrator init for a working template
```

#### "Decimal conversion error"

**Cause**: Budget value in config cannot be parsed.

**Fix:**
```toml
# Wrong
daily_limit_usd = "$10.00"  # Don't include $

# Correct
daily_limit_usd = "10.00"
```

### LM Studio Issues

#### "LM Studio connection failed"

**Cause**: LM Studio not running or wrong URL.

**Fix:**
1. Start LM Studio server:
   ```bash
   lmstudio server
   ```
2. Verify it's running:
   ```bash
   curl http://localhost:1234/v1/models
   ```
3. Update config URL if needed:
   ```toml
   [providers.lmstudio]
   base_url = "http://localhost:1234/v1"
   ```

#### "LM Studio model not loaded"

**Cause**: No model loaded in LM Studio.

**Fix:**
1. Open LM Studio GUI
2. Go to "AI Assistant" tab
3. Select and load a model
4. Then start the local server

### Performance Issues

#### "First call is slow"

**This is normal.** First calls may be slow due to:
- TLS handshake with provider
- Model warm-up on provider side
- Initial encoder loading

**Expected:** 3-10s for first call, 1-3s for subsequent calls.

#### "Tasks time out"

**Cause**: Task exceeds timeout limit.

**Fix:**
```toml
[general]
task_timeout_seconds = 600  # Increase from default 300
```

#### "Memory usage high"

**Cause**: Too many concurrent tasks or large context.

**Fix:**
- Reduce `context` size
- Process tasks sequentially
- Clear unused data from memory

### Export Issues

#### "Export file not found"

**Fix:**
```bash
# Check current directory
pwd

# Files are saved to:
ls -la cost_report_*.json
ls -la cost_report_*.csv

# Specify custom path:
orchestrator stats --export json
# Or programmatically:
tracker.save_report("/path/to/report.json")
```

## Error Messages Reference

### BudgetExceededError

```
BudgetExceededError: Daily budget exceeded after finalization: $10.0000 / $10.00
```

**Meaning**: Task completed but exceeded budget.

**Action**:
- `fail_open_with_alert` (default): Task succeeded, warning shown
- `fail_closed`: Task blocked, error raised

### KeyError: "Reservation not found"

```
KeyError: Reservation not found: abc123def456
```

**Meaning**: Tried to finalize a reservation that doesn't exist.

**Action**: Usually a bug in calling code. Ensure reservation ID is used exactly as returned.

### InvalidOperation: ConversionSyntax

```
decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]
```

**Meaning**: Budget value in config cannot be converted to Decimal.

**Action**: Ensure all budget values are strings with numeric format only:
```toml
daily_limit_usd = "10.00"  # ✓ Correct
daily_limit_usd = 10.00     # ✗ May cause issues
daily_limit_usd = "$10.00"  # ✗ Don't include $
```

### ConnectionError

```
ConnectionError: Connection refused (localhost:1234)
```

**Meaning**: Cannot connect to configured provider.

**Action**:
1. Check provider URL in config
2. Verify service is running
3. Check firewall/network settings

## Quick Diagnostic Commands

### Check Everything
```bash
orchestrator doctor
```

### View Current Stats
```bash
orchestrator stats
```

### Estimate Task Cost
```bash
orchestrator dry-run "your task description"
```

### Check API Key
```bash
echo $OPENROUTER_API_KEY | head -c 20
```

### Validate Config
```bash
python -c "from src.core.config import load_config; print(load_config())"
```

### Test Basic API Call
```python
from cost_orchestrator import ask
result = ask("Hello")
print(f"Success: {result.success}")
print(f"Cost: ${result.cost:.4f}")
```

## FAQ

### How do I know if budget warnings are working?

Run multiple tasks until you hit 80% of budget. You should see:
```
[BUDGET WARNING] $8.0000 / $10.00 (80.0%)
```

### Can I disable budget tracking?

Not recommended. Budget tracking is a core feature. If you need unlimited spending:
```toml
[budget]
daily_limit_usd = "999999.00"
```

### Do warnings reset at midnight?

Yes! Warnings reset automatically at UTC midnight. The `_current_date` flag ensures no spam.

### Can I use multiple API keys?

Currently single key per session. For multiple projects, use different config files:
```bash
orchestrator init --config /path/to/project1.toml
```

### What happens if the API fails mid-task?

The system:
1. Releases any budget reservations
2. Logs the error
3. Escalates to next tier (if applicable)
4. Continues with remaining tasks

### Is data persistent across restarts?

- Budget tracking: No, resets on restart
- Cost reports: Yes, saved to JSON/CSV files
- Config: Yes, persisted in `~/.cost_orchestrator.toml`

## Still Having Issues?

### Get Help

1. Check this document first
2. Review `orchestrator doctor` output
3. Check `orchestrator stats` for current state
4. Run `orchestrator dry-run` to isolate the issue
5. Check project issues on GitHub

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from cost_orchestrator import ask
result = ask("Your task")
```

### Enable Verbose Output

```bash
export COST_ORCHESTRATOR_LOG_LEVEL=DEBUG
```

### Collect Diagnostic Info

```bash
# System info
python --version
pip show cost-orchestrator

# Config info
orchestrator doctor

# Current state
orchestrator stats

# Environment
env | grep -E '(OPENROUTER|LM_)'
```

---

**Last Updated**: April 26, 2026
