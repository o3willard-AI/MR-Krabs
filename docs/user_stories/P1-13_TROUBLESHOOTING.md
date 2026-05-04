# Story P1-13: Troubleshooting Guide

**Priority**: P2 (Medium)  
**Estimate**: 1 day  
**Phase**: Week 7-8

---

## User Story

As a developer encountering errors  
I want clear troubleshooting guidance  
So that I can resolve issues quickly without filing issues

---

## Acceptance Criteria

### AC1: Error Classification
- [ ] Categorize errors: API, Budget, Task, Config, System
- [ ] Each category has specific solutions
- [ ] Error codes where applicable

### AC2: Common Issues Section
1. **API Key Issues**
   - "OPENROUTER_API_KEY not set" → Set environment variable
   - "API key invalid" → Generate new key from OpenRouter
   - "401 Unauthorized" → Check key format

2. **Budget Issues**
   - "Budget exceeded" → Increase budget or break task into smaller pieces
   - "Per-task limit exceeded" → Reduce task complexity
   - "Daily budget warning" → Monitor spending

3. **LM Studio Issues**
   - "Connection refused" → Check LM Studio is running
   - "Model not found" → Verify model loaded in LM Studio
   - "Timeout" → Increase timeout or simplify task

4. **Task Execution Issues**
   - "Task keeps escalating" → Task too complex, break into subtasks
   - "file_write failed" → Check file permissions
   - "Context truncation broken" → Simplify context manually

5. **Configuration Issues**
   - "Config file not found" → Run `orchestrator init`
   - "Invalid TOML syntax" → Check for syntax errors
   - "Unknown tier" → Use valid tier name

### AC3: Debug Mode
- [ ] `orchestrator run --debug` enables verbose logging
- [ ] Shows all LLM prompts and responses
- [ ] Shows budget reservation/release events
- [ ] Shows escalation decisions with reasoning
- [ ] Logs to file: `logs/orchestrator_debug.log`

### AC4: Diagnostic Commands
- [ ] `orchestrator doctor` - System health check
- [ ] `orchestrator explain <task_id>` - View task history
- [ ] `orchestrator stats` - Check budget usage
- [ ] Commands output in machine-readable format (`--json`)

### AC5: Link to Support
- [ ] Link to GitHub issues for unresolvable problems
- [ ] Include diagnostic information request
- [ ] Suggest sharing: `orchestrator stats --json`
- [ ] Suggest sharing: `orchestrator explain <task_id>`

---

## Technical Implementation

### Files to Create
1. `docs/TROUBLESHOOTING.md` - Comprehensive guide
2. `src/cli/commands.py` - Add `--debug` flag to `cmd_run`

### Implementation Notes

```python
# src/cli/commands.py

def cmd_run(args):
    """Execute a task with optional debug mode."""
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/orchestrator_debug.log'),
                logging.StreamHandler()
            ]
        )
    
    # ... existing run logic
```

---

## Testing Requirements

### Verification
- [ ] All troubleshooting steps tested
- [ ] Debug mode produces useful output
- [ ] Diagnostic commands work correctly
- [ ] Links all functional

---

## Out of Scope
- Automated error diagnosis (Phase 4)
- Interactive troubleshooting assistant (Phase 4)

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] All scenarios tested
- [ ] Guide clear and actionable
- [ ] Code reviewed and approved
