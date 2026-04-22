# Proxy Mode Evaluation

**Status**: Evaluated / Deferred to Future
**Created**: 2026-04-03

---

## What is Proxy Mode?

Instead of wrapping frameworks with code integrations, run a local HTTP proxy that intercepts OpenAI-compatible API calls. Any tool that supports `OPENAI_API_BASE` can use cost optimization without code changes.

## How It Would Work

```bash
# Start the proxy
orchestrator proxy --port 8080

# Point any tool at the proxy
export OPENAI_API_BASE=http://localhost:8080/v1
export OPENAI_API_KEY=anything  # Proxy ignores this, uses real key from config

# Your existing tool now has cost optimization
python my_existing_script.py  # No code changes needed
```

The proxy would:
1. Intercept incoming OpenAI-compatible requests
2. Route to the cheapest capable model (tier routing)
3. Track costs and enforce budgets
4. Return responses transparently
5. Log all requests for `orchestrator stats`

## Pros
- **Zero code changes** — works with any OpenAI-compatible tool
- **Framework agnostic** — no need for CrewAI, LangChain, AutoGen adapters
- **Transparent** — existing tools don't know they're being optimized
- **Universal** — works with Claude Desktop, Cursor, Continue, etc.

## Cons
- **Adds infrastructure** — another process to manage
- **Latency** — adds a network hop (~5-20ms per request)
- **Complexity** — need to handle HTTPS, streaming, error forwarding
- **Not a library concern** — this is a server feature, not a library feature
- **Conflicts with library identity** — v1 is explicitly a library, not a service

## Decision: Defer to Server Mode

Proxy mode is a compelling feature but belongs in the future server-mode product (`cost-orchestrator-server`), not the v1 library. The library's value is in its API (`ask()`, `execute_task()`), not in being a network proxy.

## When to Build

Build proxy mode when:
1. Server mode is being developed (see FUTURE_SERVER_MODE.md)
2. Users demand zero-code integration
3. We have resources for a proper HTTP server with TLS, auth, etc.

## Sketch Implementation

If built, the proxy would use `aiohttp` or `fastapi`:

```python
# src/proxy/server.py (future)
from fastapi import FastAPI
from cost_orchestrator import CostTracker, CapabilityChecker

app = FastAPI()

@app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    # Intercept request
    model = request.get("model", "gpt-4o")
    messages = request.get("messages", [])
    
    # Route through orchestrator
    tracker = CostTracker()
    result = await orchestrator.route_request(model, messages)
    
    # Track cost
    tracker.record(task_id="proxy", tier=result.tier, model=result.model, ...)
    
    return result.to_openai_response()
```

## Alternative: Use Existing Proxies

Instead of building our own, users could use existing OpenAI-compatible proxies like:
- **LiteLLM Proxy** — `litellm --model openrouter/...`
- **Open WebUI** — has built-in model routing
- **Ollama** — local model proxy with OpenAI compatibility

These already solve the proxy problem without us building infrastructure.
