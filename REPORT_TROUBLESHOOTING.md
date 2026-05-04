# Report Generation Troubleshooting Guide

This guide helps diagnose and fix issues with the report generation commands introduced in Phase 4-5.

## Commands Reference

```bash
orchestrator daily-report [days]          # Generate daily cost report
orchestrator efficiency-report            # Analyze tier efficiency
orchestrator trend-report [days]          # Analyze cost trends
orchestrator optimization-report          # Full optimization analysis
```

---

## Common Issues

### 1. "No cost data available"

**Symptoms:**
```
============================================================
  Cost-Optimized Orchestrator - Daily Report
============================================================

No cost data available. Run some tasks first.
```

**Cause:** The metrics collector has no recorded costs or tasks.

**Fix:**
1. **Run some tasks first:**
   ```bash
   orchestrator run "Hello world" --tier L0
   orchestrator run "Write Python function" --tier L1
   ```

2. **Verify metrics collection:**
   ```bash
   orchestrator stats
   ```

3. **Check metrics file:**
   ```python
   # In Python REPL
   from src.core.metrics import MetricsCollector
   collector = MetricsCollector()
   print(collector.get_summary())
   ```

---

### 2. "No tier data available"

**Symptoms:**
```
============================================================
  Cost-Optimized Orchestrator - Tier Efficiency Report
============================================================

No tier data available. Run some tasks first.
```

**Cause:** The metrics collector has no tier-specific data.

**Fix:**
1. Run tasks across different tiers:
   ```bash
   orchestrator run "Simple task" --tier L0
   orchestrator run "Complex task" --tier L2
   ```

2. Verify tier metrics:
   ```python
   from src.core.metrics import MetricsCollector
   collector = MetricsCollector()
   print(collector.get_tier_metrics())
   ```

---

### 3. "decimal.InvalidOperation: ConversionSyntax"

**Symptoms:**
```
decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]
```

**Cause:** Config file has invalid numeric values (e.g., strings where decimals expected).

**Fix:**
1. **Check config file:**
   ```bash
   cat ~/.cost_orchestrator.toml
   ```

2. **Verify numeric values:**
   ```toml
   # CORRECT
   [budget]
   daily_limit_usd = "10.00"
   warning_threshold = "0.8"
   
   # WRONG - don't use API keys or other strings
   daily_limit_usd = "fake-api-key"  # ❌
   ```

3. **Regenerate config:**
   ```bash
   orchestrator init
   ```

---

### 4. "Warning threshold type mismatch"

**Symptoms:**
```
TypeError: '>=' not supported between instances of 'decimal.Decimal' and 'str'
```

**Cause:** Config value passed as string but expected as Decimal.

**Fix:**
This is automatically handled in recent versions. If still seeing this:

1. **Update config:**
   ```toml
   warning_threshold = "0.80"  # Ensure it's a properly formatted string
   ```

2. **Or use environment variable:**
   ```bash
   export WARNING_THRESHOLD=0.80
   ```

---

### 5. "Daily costs list empty"

**Symptoms:**
```
# Trend report shows no data
Day-over-Day Changes:
  (no data)
```

**Cause:** No historical cost data exists in the metrics collector.

**Fix:**
1. **Run tasks over multiple days:**
   ```bash
   # Wait for data to accumulate
   # Or force data generation:
   for i in {1..30}; do
       orchestrator run "Task $i" --tier L0
   done
   ```

2. **Verify daily costs:**
   ```python
   from src.core.metrics import MetricsCollector
   collector = MetricsCollector()
   costs = collector.get_daily_costs_7day()
   print(f"Days with data: {len(costs)}")
   print(f"Costs: {costs}")
   ```

---

### 6. "Spending spike detection not triggering"

**Symptoms:**
```
# Expected spike detection but no warning shown
Recommendations:
  (empty)
```

**Cause:** Cost increase is below the 50% threshold.

**Explanation:**
The spike detection only triggers when day-over-day increase exceeds 50%.

**Fix:**
1. **Check actual increase:**
   ```bash
   # Compare two consecutive days manually
   orchestrator trend-report 1
   orchestrator trend-report 2
   ```

2. **If you want lower threshold:**
   Modify `src/reports/trend_analysis.py`:
   ```python
   # Change from 0.50 to your preferred threshold
   if change > Decimal("0.50"):  # 50%
   # to
   if change > Decimal("0.30"):  # 30%
   ```

---

### 7. "Cost projection fails"

**Symptoms:**
```
# Projection calculation error
```

**Cause:** Insufficient data for projection (need at least 7 days).

**Fix:**
1. **Ensure 7+ days of data:**
   ```python
   from src.core.metrics import MetricsCollector
   collector = MetricsCollector()
   costs = collector.get_daily_costs_7day()
   print(f"Days available: {len(costs)}")
   ```

2. **Accumulate data over time:**
   Reports work best after running tasks for a week.

---

### 8. "Tier efficiency score shows 0"

**Symptoms:**
```
Tier Efficiency Rankings:
1     L0-Coder     0       $0.00          0.0%          0 tasks
```

**Cause:** No task data or all tasks failed.

**Fix:**
1. **Check task success rate:**
   ```python
   from src.core.metrics import MetricsCollector
   collector = MetricsCollector()
   metrics = collector.get_tier_metrics()
   for tier, data in metrics.items():
       success_rate = data['success_count'] / data['count'] * 100
       print(f"{tier}: {success_rate:.1f}% success rate")
   ```

2. **Verify tasks are completing successfully:**
   ```bash
   orchestrator run "Test task" --tier L0 --verbose
   ```

---

### 9. "Report output incomplete"

**Symptoms:**
```
============================================================
  Cost-Optimized Orchestrator - Daily Report
============================================================

Budget Status:
----------------------------------------
  Daily Limit:      $100.00
  # (truncated)
```

**Cause:** Terminal width too narrow or output truncated.

**Fix:**
1. **Increase terminal width** or
2. **Redirect to file:**
   ```bash
   orchestrator daily-report > report.txt
   cat report.txt
   ```
3. **Use verbose flag if available:**
   ```bash
   orchestrator daily-report --verbose
   ```

---

### 10. "Config loading error"

**Symptoms:**
```
Config file not found or invalid
```

**Fix:**
1. **Check if config exists:**
   ```bash
   ls -la ~/.cost_orchestrator.toml
   ```

2. **If missing, create one:**
   ```bash
   orchestrator init
   ```

3. **Verify TOML syntax:**
   ```bash
   # Test TOML parsing
   python -c "import tomllib; tomllib.load(open('.cost_orchestrator.toml', 'rb'))"
   ```

---

## Debug Mode

Enable verbose debugging for report commands:

```bash
# Set debug environment variable
export DEBUG_REPORTS=1

# Then run any report command
orchestrator daily-report
```

This will show:
- Config values being loaded
- Metrics data being queried
- Calculation steps
- Any errors in detail

---

## Verification Checklist

Before troubleshooting, verify:

- [ ] API key is set (`echo $OPENROUTER_API_KEY`)
- [ ] Config file exists (`~/.cost_orchestrator.toml`)
- [ ] Some tasks have been run (`orchestrator stats`)
- [ ] Config values are valid TOML format
- [ ] No syntax errors in config (use `orchestrator doctor`)

---

## Getting Help

If issues persist:

1. **Check existing issues** on the project repository
2. **Run `orchestrator doctor`** to diagnose system issues
3. **Enable debug mode** (see above)
4. **File an issue** with:
   - Full error message
   - Config file contents (with API key masked)
   - Steps to reproduce
   - Debug output if available

---

## Performance Notes

Report commands are fast but may take longer with:
- Large historical data (1000+ tasks)
- 30-day trend analysis
- Comprehensive optimization reports

Expected times:
- Daily report: <1 second
- Efficiency report: <2 seconds
- Trend report (7 days): <3 seconds
- Optimization report: <5 seconds

---

## Related Documentation

- [README.md](README.md#cli-commands) - Main command reference
- [Phase 4-5 Story Cards](docs/stories/p4-5.md) - Feature specifications
- [Unit Test Coverage](tests/unit/test_cli_report_commands_p4_5.py) - Test examples
