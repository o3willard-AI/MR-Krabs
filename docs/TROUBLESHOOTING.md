# Troubleshooting & FAQ

## Common Issues

### Why is my task escalating to L3 every time?

**Cause**: The L0 model may not support the task type (e.g., tool calling, complex reasoning).

**Fix**:
1. Check model capabilities: `from cost_orchestrator.model_capabilities import CapabilityChecker`
2. Verify the model supports required features (tool calling, context window)
3. Consider starting at a higher tier for complex tasks

### Why is cost showing $0.00?

**Cause**: You may be using a local model (LM Studio) which has no API cost, or token counting isn't working.

**Fix**:
1. If using LM Studio: $0.00 is correct (local models are free)
2. If using OpenRouter: Check that your API key is set and responses include token usage
3. Run `orchestrator doctor` to verify configuration

### Can I use this without OpenRouter?

**Yes**. Set up an alternative provider:

```toml
[providers.lmstudio]
base_url = "http://localhost:1234/v1"
```

Or use any OpenAI-compatible API endpoint.

### Does this work with streaming?

Streaming support is planned but not yet implemented. The current implementation uses request-response calls.

### What happens if I go over budget?

By default, the system uses `fail_open_with_alert` mode:
- Tasks continue but warnings are logged
- An emergency cap ($5.00 default) provides a hard stop
- Set `failure_mode = "fail_closed"` in config to block immediately

## Error Messages

### "Budget reservation failed"

**What**: Your estimated cost would exceed the daily budget.
**Fix**: Increase your daily budget or reduce task complexity.

### "Task timed out"

**What**: The task exceeded the global timeout (default: 300s).
**Fix**: Increase `task_timeout_seconds` in config or simplify the task.

### "Model does not support tool calling"

**What**: The assigned model can't execute tool calls required by the task.
**Fix**: Use a model with tool-calling support (check model capabilities registry).

### "Connection refused"

**What**: Cannot connect to the LLM provider.
**Fix**: 
1. Check network connectivity
2. Verify the provider URL is correct
3. For LM Studio: ensure it's running at the configured host

## Performance

### Why is the first call slow?

The first call may be slower due to:
- TLS handshake with the provider
- Model warm-up on the provider side
- Initial token encoder loading

Subsequent calls should be faster.

### How do I know it's working?

After each task, you should see a one-line summary:
```
[orchestrator] Task completed: L0, $0.00, saved ~$0.12 vs. GPT-4o
```

Run `orchestrator stats` to see overall spending and savings.
