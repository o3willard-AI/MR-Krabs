# Technical Design Decisions

## Version
1.0

## Date
April 3, 2026

## Overview

This document resolves open architectural questions and provides concrete designs for critical subsystems that were previously underspecified in the system architecture.

---

## 1. Context Simplification Algorithm

### 1.1 Problem

When a task fails at a tier, retrying with the same prompt is unlikely to succeed. The system needs a deterministic, low-cost way to simplify context before retry, and before escalation to a higher tier.

### 1.2 Design: Multi-Strategy Context Simplification

Context simplification uses a **layered strategy** that does NOT require an additional LLM call. Each retry applies progressively more aggressive reduction:

```
Attempt 1: 100% context (original)
Attempt 2: 70% context (trim + summarize metadata)
Attempt 3: 40% context (essential-only)
```

### 1.3 Simplification Strategies

#### Strategy A: Structural Truncation (Attempt 2)

```python
def simplify_structural(context: str, target_ratio: float) -> str:
    """Preserve beginning and end, truncate middle."""
    lines = context.split('\n')
    keep = int(len(lines) * target_ratio)
    head = lines[:keep // 2]
    tail = lines[-(keep - len(head)):]
    return '\n'.join(head + ['... [context truncated for retry] ...'] + tail)
```

**Rationale**: LLMs exhibit positional bias — they pay most attention to the beginning and end of context. Preserving these regions maintains instruction fidelity while reducing noise.

#### Strategy B: Section-Aware Reduction (Attempt 2, preferred when available)

If context is structured (e.g., XML tags, markdown headers, JSON), reduce by section priority:

```python
SECTION_PRIORITY = {
    'system_prompt': 1.0,      # Never truncate
    'instructions': 1.0,        # Never truncate
    'examples': 0.5,            # Keep 1 example, drop rest
    'context_files': 0.3,       # Keep only relevant file excerpts
    'previous_errors': 0.8,     # Keep error messages, drop stack traces
    'output_format': 1.0,       # Never truncate
}

def simplify_section_aware(context: StructuredContext, target_ratio: float) -> str:
    """Reduce context by section priority."""
    budget = estimate_tokens(context.full_text) * target_ratio
    result = {}
    
    # Allocate budget by priority (highest priority gets full allocation first)
    for section, priority in sorted(SECTION_PRIORITY.items(), key=lambda x: -x[1]):
        section_text = context.sections.get(section, '')
        section_tokens = estimate_tokens(section_text)
        allocated = min(section_tokens, budget)
        result[section] = truncate_to_tokens(section_text, allocated)
        budget -= allocated
    
    return assemble_context(result)
```

#### Strategy C: Essential-Only Mode (Attempt 3)

For the final retry before escalation, strip everything except the core task:

```python
def simplify_essential(task: Task, context: StructuredContext) -> str:
    """Build minimal context containing only task essentials."""
    return assemble_context({
        'system_prompt': context.sections['system_prompt'],
        'instructions': task.description,
        'output_format': context.sections.get('output_format', ''),
        'error_summary': summarize_last_error(context.last_error),
    })
```

The `summarize_last_error` function extracts only:
- Error type (e.g., "SyntaxError", "TimeoutError", "RateLimitError")
- Error message (first 200 chars)
- Failed file/line if available

### 1.4 Context Simplification Configuration

```yaml
context_simplification:
  strategy: "section_aware"  # "structural" | "section_aware" | "essential_only"
  levels:
    - ratio: 1.0
      description: "Full context (initial attempt)"
    - ratio: 0.7
      description: "Structural truncation or section-aware reduction"
    - ratio: 0.4
      description: "Essential-only mode"
  preserve_always:
    - "system_prompt"
    - "instructions"
    - "output_format"
```

### 1.5 Token Estimation

For simplification, we use a fast approximation (not the provider's exact tokenizer):

```python
def estimate_tokens(text: str) -> int:
    """Fast approximation: ~4 chars per token for English text."""
    return len(text) // 4
```

This is sufficient for ratio-based reduction. Exact token counting happens at the provider layer for billing.

### 1.6 File Context Pruning

When context includes file contents, the `ContextPruner` identifies relevant files:

```python
class ContextPruner:
    def prune_files(self, task: Task, files: list[FileRef], max_files: int = 5) -> list[FileRef]:
        """Select most relevant files based on task description similarity."""
        # Simple TF-IDF or keyword matching between task description and file paths/content
        scored = [(self.relevance_score(task.description, f), f) for f in files]
        scored.sort(reverse=True)
        return [f for _, f in scored[:max_files]]
    
    def truncate_file(self, file: FileRef, max_lines: int = 100) -> str:
        """Keep function/class signatures, truncate bodies."""
        # For Python: keep def/class lines and docstrings, replace bodies with "..."
        # For JS/TS: keep function/export signatures, replace bodies
        pass
```

---

## 2. Circuit Breaker Pattern

### 2.1 Problem

If a provider is degraded (high latency, elevated error rates), continuing to send it traffic wastes user budget and time. The system needs to detect degradation and temporarily route around it.

### 2.2 Design: Three-State Circuit Breaker

Each provider adapter wraps its calls with a circuit breaker:

```
States:
  CLOSED    → Normal operation, requests flow through
  OPEN      → Provider is degraded, requests fail immediately
  HALF_OPEN → Testing if provider recovered, limited requests allowed

Transitions:
  CLOSED → OPEN:        When failure_rate > threshold within window
  OPEN → HALF_OPEN:     After cooldown_period expires
  HALF_OPEN → CLOSED:   When test requests succeed
  HALF_OPEN → OPEN:     When any test request fails
```

### 2.3 Circuit Breaker Configuration

```yaml
circuit_breaker:
  enabled: true
  failure_threshold: 0.5        # 50% failure rate triggers open
  sample_size: 10               # Minimum requests before evaluating
  cooldown_period_seconds: 60   # How long to wait before testing recovery
  half_open_max_requests: 3     # Concurrent test requests in half-open state
  
  # Per-provider overrides
  providers:
    openrouter:
      failure_threshold: 0.3    # More sensitive for paid provider
      cooldown_period_seconds: 120
    lmstudio:
      failure_threshold: 0.7    # More tolerant for local (often transient)
      cooldown_period_seconds: 30
```

### 2.4 Circuit Breaker Implementation

```python
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreaker:
    provider: str
    failure_threshold: float = 0.5
    sample_size: int = 10
    cooldown_seconds: int = 60
    half_open_max: int = 3
    
    _state: CircuitState = CircuitState.CLOSED
    _failures: int = 0
    _successes: int = 0
    _total: int = 0
    _opened_at: datetime | None = None
    _half_open_in_flight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def can_execute(self) -> bool:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if datetime.now() - self._opened_at > timedelta(seconds=self.cooldown_seconds):
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_flight = 0
                    return True
                return False
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight < self.half_open_max:
                    self._half_open_in_flight += 1
                    return True
                return False
            return False
    
    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.half_open_max:
                    self._reset()
            else:
                self._successes += 1
                self._total += 1
                self._check_threshold()
    
    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._total += 1
            if self._state == CircuitState.HALF_OPEN:
                self._open()
            else:
                self._check_threshold()
    
    def _check_threshold(self):
        if self._total >= self.sample_size:
            rate = self._failures / self._total
            if rate >= self.failure_threshold:
                self._open()
    
    def _open(self):
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now()
    
    def _reset(self):
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._total = 0
        self._opened_at = None
        self._half_open_in_flight = 0
```

### 2.5 Integration with Escalation Engine

When a circuit is OPEN, the Escalation Engine skips that provider and either:
1. Falls back to another model in the same tier (if available)
2. Escalates to the next tier immediately (without using retries)

```python
def execute_with_circuit_breaker(self, tier_config, prompt):
    provider = tier_config['provider']
    if not self.circuit_breakers[provider].can_execute():
        logger.warning(f"Circuit OPEN for {provider}, skipping to fallback")
        return self._try_fallback(tier_config, prompt)
    
    try:
        result = self.provider_call(tier_config, prompt)
        self.circuit_breakers[provider].record_success()
        return result
    except ProviderError as e:
        self.circuit_breakers[provider].record_failure()
        raise
```

### 2.6 Observability

Circuit breaker state changes emit structured events:

```json
{
  "event": "circuit_state_change",
  "provider": "openrouter",
  "from_state": "closed",
  "to_state": "open",
  "failure_rate": 0.6,
  "sample_size": 15,
  "timestamp": "2026-04-03T14:32:00Z"
}
```

---

## 3. Budget Tracking Failure Mode

### 3.1 Problem

If the storage backend (SQLite/PostgreSQL) is unavailable when checking or recording budget, the system must decide: fail open (allow calls, risking budget overrun) or fail closed (block calls, preventing work).

### 3.2 Decision: Fail Closed by Default, Configurable

The default behavior is **fail closed** — if budget cannot be verified, the task is rejected. This protects users from unexpected charges. However, this is configurable for environments where availability is more critical than cost control.

### 3.3 Failure Mode Configuration

```yaml
budget:
  failure_mode: "fail_closed"  # "fail_closed" | "fail_open" | "fail_open_with_alert"
  
  # When fail_open_with_alert is set:
  fail_open_alert:
    max_untracked_calls: 5     # Maximum calls allowed while storage is down
    emergency_cap_usd: 2.00    # Hard cap on untracked spending
```

### 3.4 Behavior Matrix

| Scenario | fail_closed | fail_open | fail_open_with_alert |
|----------|-------------|-----------|---------------------|
| DB unavailable at check | Reject task | Allow task | Allow task (up to 5) |
| DB unavailable at record | Reject task | Allow, log warning | Allow, log warning |
| DB recovered | N/A | Reconcile pending spends | Reconcile, alert if over cap |
| Emergency cap exceeded | N/A | N/A | Reject task, send alert |

### 3.5 Implementation

```python
class BudgetEnforcer:
    def check_budget(self, scope: str, estimated_cost: float) -> BudgetDecision:
        try:
            budget = self.storage.get_budget(scope)
            spending = self.storage.get_spending(scope)
            remaining = budget.limit - spending
            
            if remaining < estimated_cost:
                return BudgetDecision.REJECTED(reason="Budget exceeded")
            
            if remaining < budget.limit * (1 - budget.warning_threshold):
                return BudgetDecision.ALLOWED_WITH_WARNING(
                    remaining=remaining,
                    message=f"Budget warning: {remaining:.2f} USD remaining"
                )
            
            return BudgetDecision.ALLOWED
            
        except StorageError as e:
            mode = self.config.failure_mode
            
            if mode == "fail_closed":
                logger.error(f"Storage unavailable, rejecting task (fail_closed): {e}")
                return BudgetDecision.REJECTED(reason="Budget check unavailable")
            
            if mode == "fail_open":
                logger.warning(f"Storage unavailable, allowing task (fail_open): {e}")
                return BudgetDecision.ALLOWED_UNTRACKED(reason="Budget check unavailable")
            
            if mode == "fail_open_with_alert":
                untracked = self._get_untracked_count(scope)
                if untracked >= self.config.fail_open_alert.max_untracked_calls:
                    return BudgetDecision.REJECTED(reason="Emergency cap reached")
                self._increment_untracked(scope)
                return BudgetDecision.ALLOWED_UNTRACKED(reason="Budget check unavailable (emergency mode)")
    
    def record_spending(self, scope: str, amount: float):
        try:
            self.storage.record_spending(scope, amount)
        except StorageError as e:
            logger.error(f"Failed to record spending: {e}")
            self._queue_pending_spend(scope, amount)
```

### 3.6 Pending Spend Reconciliation

When storage recovers, pending spends are reconciled:

```python
def reconcile_pending_spends(self):
    """Called when storage connection is restored."""
    for scope, amount in self._pending_spends:
        try:
            self.storage.record_spending(scope, amount)
        except StorageError:
            logger.error(f"Still cannot record pending spend: {scope} ${amount}")
    self._pending_spends.clear()
```

---

## 4. Unified Token Counting Strategy

### 4.1 Problem

Different LLM providers use different tokenizers (OpenAI uses tiktoken, Anthropic uses their own, open-source models vary). Accurate cost calculation requires knowing the exact token count, but we need a consistent interface.

### 4.2 Design: Provider-Delegated Token Counting with Local Fallback

The strategy has two layers:

1. **Primary**: Ask the provider to count tokens (most accurate, requires API call)
2. **Fallback**: Use a local tokenizer approximation (fast, no API call)

### 4.3 Token Counter Interface

```python
from abc import ABC, abstractmethod

class TokenCounter(ABC):
    @abstractmethod
    async def count_prompt_tokens(self, messages: list[dict], model: str) -> int:
        """Count tokens in the prompt (messages array)."""
        pass
    
    @abstractmethod
    async def count_completion_tokens(self, text: str, model: str) -> int:
        """Count tokens in the completion text."""
        pass
    
    @abstractmethod
    def estimate_tokens(self, text: str, model: str) -> int:
        """Fast local estimation (no API call). Used for budget pre-checks."""
        pass
```

### 4.4 Provider-Specific Implementations

#### OpenRouter Adapter

OpenRouter's API returns `usage` in the response. We use this for accurate post-call counting:

```python
class OpenRouterTokenCounter(TokenCounter):
    def __init__(self, client):
        self.client = client
        self._local_counter = TiktokenCounter()  # Fallback
    
    async def count_prompt_tokens(self, messages, model):
        # OpenRouter returns usage in the response, so we count after the call
        # For pre-call estimation, use local counter
        return self._local_counter.count(messages, model)
    
    def estimate_tokens(self, text, model):
        return self._local_counter.estimate(text, model)
```

For pre-call budget checks, we use `tiktoken` for OpenAI-compatible models:

```python
class TiktokenCounter:
    def __init__(self):
        self._encoders = {}
    
    def _get_encoder(self, model: str):
        if model not in self._encoders:
            import tiktoken
            try:
                self._encoders[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                self._encoders[model] = tiktoken.get_encoding("cl100k_base")
        return self._encoders[model]
    
    def count(self, messages: list[dict], model: str) -> int:
        encoder = self._get_encoder(model)
        # Per OpenAI's token counting formula
        tokens_per_message = 3
        tokens_per_name = 1
        num_tokens = 0
        for msg in messages:
            num_tokens += tokens_per_message
            for key, value in msg.items():
                num_tokens += len(encoder.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # Every reply is primed with <|start|>assistant<|message|>
        return num_tokens
    
    def estimate(self, text: str, model: str) -> int:
        """Fast approximation: ~4 chars/token for English."""
        return len(text) // 4
```

#### Anthropic Adapter

```python
class AnthropicTokenCounter(TokenCounter):
    def __init__(self, client):
        self.client = client
    
    async def count_prompt_tokens(self, messages, model):
        # Anthropic API has a count_tokens endpoint
        response = await self.client.messages.count_tokens(
            model=model,
            messages=messages
        )
        return response.input_tokens
    
    def estimate_tokens(self, text, model):
        # Claude uses a custom tokenizer; approximate with 3.5 chars/token
        return len(text) // 3.5
```

#### LM Studio Adapter

```python
class LMStudioTokenCounter(TokenCounter):
    def estimate_tokens(self, text, model):
        # Local models vary widely; use conservative 4 chars/token
        return len(text) // 4
```

### 4.5 Token Counting Flow

```
1. Pre-call budget check:
   orchestrator.estimate_cost(task) 
   → token_counter.estimate_tokens(prompt, model)  # Fast local approx
   → check against budget

2. Post-call accurate tracking:
   provider.execute(prompt) 
   → response.usage.prompt_tokens   # From provider API
   → response.usage.completion_tokens
   → cost_tracker.record(tokens, cost)
```

### 4.6 Token Counting Accuracy Requirements

| Provider | Pre-call estimate accuracy | Post-call accuracy |
|----------|---------------------------|-------------------|
| OpenAI/OpenRouter | ±15% (sufficient for budget check) | Exact (from API response) |
| Anthropic | ±20% | Exact (from API response) |
| LM Studio | ±25% | Exact (if model supports it) |

Pre-call estimates are only used for budget pre-checks. Actual billing always uses post-call exact counts from the provider.

---

## 5. OpenTelemetry Observability

### 5.1 Problem

The architecture mentions Prometheus but not OpenTelemetry (OTel), which is the industry standard for traces, metrics, and logs. Without OTel, integration with modern observability stacks (Honeycomb, Grafana Cloud, Datadog, Jaeger) is limited.

### 5.2 Decision: OpenTelemetry as Primary Observability Standard

All observability goes through OpenTelemetry. Prometheus metrics are exposed via the OTel Prometheus exporter for backward compatibility.

### 5.3 OTel Instrumentation

#### Traces

Each task execution produces a trace with spans for each tier attempt:

```python
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer("cost_orchestrator")
meter = metrics.get_meter("cost_orchestrator")

class Orchestrator:
    async def execute_task(self, task_id, description, initial_tier):
        with tracer.start_as_current_span(
            "task.execute",
            attributes={
                "task.id": task_id,
                "task.description": description,
                "task.initial_tier": initial_tier,
            }
        ) as span:
            result = await self._run_escalation_loop(task_id, description, initial_tier)
            
            span.set_attribute("task.success", result.success)
            span.set_attribute("task.total_cost_usd", result.total_cost)
            span.set_attribute("task.tiers_used", result.tiers_used)
            span.set_attribute("task.attempts", result.total_attempts)
            
            if result.success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, result.error))
            
            return result
    
    async def _run_tier_attempt(self, tier, model, prompt):
        with tracer.start_as_current_span(
            "tier.attempt",
            attributes={
                "tier.name": tier,
                "tier.model": model,
                "tier.attempt_number": self._current_attempt,
            }
        ) as span:
            # Circuit breaker check
            if not self.circuit_breaker.can_execute(model):
                span.set_attribute("circuit_breaker.open", True)
                raise CircuitOpenError(f"Circuit open for {model}")
            
            # Provider call
            start = time.monotonic()
            try:
                response = await self.provider.call(model, prompt)
                duration = time.monotonic() - start
                
                span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
                span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
                span.set_attribute("llm.cost_usd", response.cost)
                span.set_attribute("llm.duration_ms", duration * 1000)
                span.set_status(Status(StatusCode.OK))
                
                return response
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
```

#### Metrics

```python
# Counters
task_execution_counter = meter.create_counter(
    "orchestrator.task.executions",
    description="Total task executions",
    unit="1"
)

cost_counter = meter.create_counter(
    "orchestrator.cost.total_usd",
    description="Total cost in USD",
    unit="USD"
)

token_counter = meter.create_counter(
    "orchestrator.tokens.total",
    description="Total tokens used",
    unit="token"
)

# Histograms
task_duration_histogram = meter.create_histogram(
    "orchestrator.task.duration_ms",
    description="Task execution duration",
    unit="ms"
)

cost_per_task_histogram = meter.create_histogram(
    "orchestrator.cost.per_task_usd",
    description="Cost per task",
    unit="USD"
)

# UpDownGauges
budget_remaining_gauge = meter.create_up_down_counter(
    "orchestrator.budget.remaining_usd",
    description="Remaining budget",
    unit="USD"
)

circuit_breaker_gauge = meter.create_up_down_counter(
    "orchestrator.circuit_breaker.state",
    description="Circuit breaker state (0=closed, 1=half_open, 2=open)",
    unit="1"
)
```

#### Logs

Structured logging via `structlog` with OTel correlation:

```python
import structlog
from opentelemetry.trace import get_current_span

logger = structlog.get_logger()

def log_with_trace_context(event: str, **kwargs):
    span = get_current_span()
    if span.is_recording():
        ctx = span.get_span_context()
        kwargs["trace_id"] = f"{ctx.trace_id:032x}"
        kwargs["span_id"] = f"{ctx.span_id:016x}"
    logger.info(event, **kwargs)
```

### 5.4 Exporter Configuration

```yaml
observability:
  opentelemetry:
    enabled: true
    
    # Exporters (can use multiple)
    exporters:
      console:
        enabled: false  # Debug only
      
      prometheus:
        enabled: true
        port: 9090
        path: "/metrics"
      
      otlp:
        enabled: false  # Send to OTel collector
        endpoint: "localhost:4317"
        protocol: "grpc"
      
      jaeger:
        enabled: false
        endpoint: "localhost:14250"
    
    # Sampling
    sampling:
      type: "parent_based"
      root: "traceidratio"
      ratio: 0.1  # 10% of traces sampled by default
    
    # Resource attributes
    resource:
      service.name: "cost-orchestrator"
      service.version: "1.0.0"
      deployment.environment: "production"
```

### 5.5 Prometheus Metrics (via OTel)

The following metrics are exposed at `/metrics` for Prometheus scraping:

```
# HELP orchestrator_task_executions_total Total task executions
# TYPE orchestrator_task_executions_total counter
orchestrator_task_executions_total{tier="L0-Coder",success="true"} 1523
orchestrator_task_executions_total{tier="L1-Coder",success="true"} 234
orchestrator_task_executions_total{tier="L0-Coder",success="false"} 45

# HELP orchestrator_cost_total_usd Total cost in USD
# TYPE orchestrator_cost_total_usd counter
orchestrator_cost_total_usd{provider="openrouter"} 12.45
orchestrator_cost_total_usd{provider="lmstudio"} 0.00

# HELP orchestrator_task_duration_ms Task execution duration
# TYPE orchestrator_task_duration_ms histogram
orchestrator_task_duration_ms_bucket{tier="L0-Coder",le="1000"} 1200
orchestrator_task_duration_ms_bucket{tier="L0-Coder",le="5000"} 1450
orchestrator_task_duration_ms_bucket{tier="L0-Coder",le="+Inf"} 1523

# HELP orchestrator_circuit_breaker_state Circuit breaker state
# TYPE orchestrator_circuit_breaker_state gauge
orchestrator_circuit_breaker_state{provider="openrouter"} 0
orchestrator_circuit_breaker_state{provider="lmstudio"} 0

# HELP orchestrator_budget_remaining_usd Remaining budget
# TYPE orchestrator_budget_remaining_usd gauge
orchestrator_budget_remaining_usd{scope="project:webapp"} 487.55
```

---

## 6. Error Classification Taxonomy

### 6.1 Problem

The `FailureAnalyzer` needs to distinguish between different failure types to make intelligent retry/escalation decisions. A timeout should be retried; a rate limit should be delayed; a hallucination should be escalated.

### 6.2 Error Taxonomy

```python
from enum import Enum

class ErrorCategory(Enum):
    """Top-level error categories."""
    TRANSIENT = "transient"           # Retry may succeed
    RATE_LIMIT = "rate_limit"         # Back off and retry
    CONTEXT = "context"               # Context too large or malformed
    MODEL_CAPABILITY = "model_capability"  # Model can't handle task
    VALIDATION = "validation"         # Output doesn't meet criteria
    AUTHENTICATION = "authentication" # API key or auth issue
    INFRASTRUCTURE = "infrastructure" # Network, DNS, etc.
    BUDGET = "budget"                 # Budget exceeded
    CIRCUIT_BREAKER = "circuit_breaker"  # Circuit is open

class ErrorAction(Enum):
    """Recommended action for each error category."""
    RETRY = "retry"                   # Retry same tier, same provider
    RETRY_WITH_DELAY = "retry_delay"  # Retry after backoff
    RETRY_SIMPLIFIED = "retry_simplified"  # Retry with simplified context
    ESCALATE = "escalate"             # Move to next tier
    FAIL = "fail"                     # Cannot recover
    SWITCH_PROVIDER = "switch_provider"  # Try different provider, same tier
```

### 6.3 Error Classification Map

```python
ERROR_CLASSIFICATION = {
    # Transient errors
    "TimeoutError": (ErrorCategory.TRANSIENT, ErrorAction.RETRY_WITH_DELAY),
    "ConnectionError": (ErrorCategory.TRANSIENT, ErrorAction.RETRY_WITH_DELAY),
    "ConnectionRefusedError": (ErrorCategory.TRANSIENT, ErrorAction.RETRY_WITH_DELAY),
    
    # Rate limits
    "RateLimitError": (ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    "TooManyRequestsError": (ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    "429": (ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    
    # Context errors
    "ContextLengthExceeded": (ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    "MaxTokensExceeded": (ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    "context_length_exceeded": (ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    
    # Model capability
    "ContentPolicyViolation": (ErrorCategory.MODEL_CAPABILITY, ErrorAction.ESCALATE),
    "refusal": (ErrorCategory.MODEL_CAPABILITY, ErrorAction.ESCALATE),
    
    # Validation errors (output doesn't meet criteria)
    "ValidationError": (ErrorCategory.VALIDATION, ErrorAction.RETRY_SIMPLIFIED),
    "OutputFormatError": (ErrorCategory.VALIDATION, ErrorAction.RETRY_SIMPLIFIED),
    "SchemaValidationError": (ErrorCategory.VALIDATION, ErrorAction.RETRY_SIMPLIFIED),
    
    # Authentication
    "AuthenticationError": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    "InvalidApiKey": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    "401": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    "403": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    
    # Infrastructure
    "DNSResolutionError": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "SSLError": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "502": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "503": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "504": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    
    # Budget
    "BudgetExceeded": (ErrorCategory.BUDGET, ErrorAction.FAIL),
    
    # Circuit breaker
    "CircuitOpen": (ErrorCategory.CIRCUIT_BREAKER, ErrorAction.SWITCH_PROVIDER),
}
```

### 6.4 FailureAnalyzer Implementation

```python
@dataclass
class FailureAnalysis:
    category: ErrorCategory
    action: ErrorAction
    confidence: float  # 0.0-1.0, how confident we are in the classification
    details: str
    retry_delay_seconds: float = 0.0
    suggestion: str = ""

class FailureAnalyzer:
    def analyze(self, error: Exception, context: ExecutionContext) -> FailureAnalysis:
        """Classify an error and recommend action."""
        
        # Step 1: Match by exception type
        error_type = type(error).__name__
        if error_type in ERROR_CLASSIFICATION:
            category, action = ERROR_CLASSIFICATION[error_type]
            return FailureAnalysis(
                category=category,
                action=action,
                confidence=0.9,
                details=f"Matched by exception type: {error_type}",
                retry_delay_seconds=self._calculate_backoff(context.attempt),
            )
        
        # Step 2: Match by error message content
        error_message = str(error).lower()
        for pattern, (category, action) in ERROR_CLASSIFICATION.items():
            if pattern.lower() in error_message:
                return FailureAnalysis(
                    category=category,
                    action=action,
                    confidence=0.7,
                    details=f"Matched by error message: {pattern}",
                    retry_delay_seconds=self._calculate_backoff(context.attempt),
                )
        
        # Step 3: Match by HTTP status code
        if hasattr(error, 'status_code'):
            status_code = str(error.status_code)
            if status_code in ERROR_CLASSIFICATION:
                category, action = ERROR_CLASSIFICATION[status_code]
                return FailureAnalysis(
                    category=category,
                    action=action,
                    confidence=0.85,
                    details=f"Matched by HTTP status: {status_code}",
                    retry_delay_seconds=self._calculate_backoff(context.attempt),
                )
        
        # Step 4: Default - unknown error, escalate
        return FailureAnalysis(
            category=ErrorCategory.TRANSIENT,
            action=ErrorAction.ESCALATE,
            confidence=0.3,
            details=f"Unknown error: {error_type}: {error}",
            retry_delay_seconds=self._calculate_backoff(context.attempt),
            suggestion="Consider adding this error type to the classification map",
        )
    
    def _calculate_backoff(self, attempt: int, base_delay: float = 2.0) -> float:
        """Exponential backoff with jitter."""
        import random
        delay = base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.5)
        return delay + jitter
    
    def should_escalate(self, analysis: FailureAnalysis) -> bool:
        """Determine if escalation is warranted."""
        return analysis.action in (ErrorAction.ESCALATE, ErrorAction.FAIL)
    
    def should_retry(self, analysis: FailureAnalysis, attempt: int, max_retries: int) -> bool:
        """Determine if retry is warranted."""
        if analysis.action == ErrorAction.FAIL:
            return False
        if analysis.action == ErrorAction.ESCALATE:
            return False
        return attempt < max_retries
```

### 6.5 Error Classification Metrics

Each error classification is tracked as a metric:

```
orchestrator_errors_total{category="transient",tier="L0-Coder"} 12
orchestrator_errors_total{category="rate_limit",tier="L1-Coder"} 3
orchestrator_errors_total{category="model_capability",tier="L0-Coder"} 45
orchestrator_errors_total{category="context",tier="L0-Coder"} 8
```

---

## 7. Data Retention Policy

### 7.1 Problem

Execution records contain metadata about LLM calls (costs, models, success rates) and optionally prompt/response content. Without a clear retention policy, databases grow unbounded and may contain sensitive data longer than necessary.

### 7.2 Default Retention Policy

| Data Type | Default Retention | Rationale |
|-----------|------------------|-----------|
| Execution records (metadata only) | 90 days | Sufficient for trend analysis and billing |
| Execution records (with prompt/response) | 7 days | Only stored if `log_prompts: true` |
| Budget records | 365 days | Needed for annual cost reporting |
| Tier statistics (aggregated) | Indefinite | Small, anonymized, no sensitive data |
| Audit logs | 365 days | Compliance and debugging |
| Circuit breaker state | 7 days | Ephemeral, resets on restart |

### 7.3 Retention Configuration

```yaml
data_retention:
  # What to store
  log_prompts: false          # Never store prompt/response content by default
  log_responses: false        # Never store response content by default
  log_errors: true            # Always store error messages
  log_metadata: true          # Always store execution metadata
  
  # How long to keep it
  retention_days:
    execution_metadata: 90
    execution_content: 7      # Only applies if log_prompts/log_responses is true
    budget_records: 365
    tier_statistics: -1       # -1 = indefinite
    audit_logs: 365
    circuit_state: 7
  
  # Cleanup
  cleanup:
    enabled: true
    schedule: "daily"         # Run cleanup daily
    batch_size: 1000          # Delete in batches to avoid long locks
    dry_run: false            # Set to true to log what would be deleted
```

### 7.4 Cleanup Implementation

```python
class DataRetentionManager:
    async def run_cleanup(self):
        """Delete records past their retention period."""
        cutoffs = {
            'execution_metadata': datetime.now() - timedelta(days=self.config.retention_days['execution_metadata']),
            'execution_content': datetime.now() - timedelta(days=self.config.retention_days['execution_content']),
            'audit_logs': datetime.now() - timedelta(days=self.config.retention_days['audit_logs']),
            'circuit_state': datetime.now() - timedelta(days=self.config.retention_days['circuit_state']),
        }
        
        for table, cutoff in cutoffs.items():
            deleted = 0
            while True:
                result = await self.storage.delete_old_records(
                    table, cutoff, limit=self.config.cleanup.batch_size
                )
                deleted += result.deleted_count
                if result.deleted_count < self.config.cleanup.batch_size:
                    break
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} records from {table}")
```

### 7.5 Privacy Considerations

- **Prompt/response logging is OFF by default**. Users must explicitly opt in.
- **No prompt data is ever sent externally** for analytics or ML training.
- **Tier statistics are aggregated** and contain no prompt/response content.
- **Export on request**: Users can export all their data (GDPR Article 20 compliance).
- **Delete on request**: Users can delete all their data (GDPR Article 17 compliance).

```yaml
privacy:
  # Never share data externally
  share_anonymized_data: false
  
  # User data controls
  export_on_request: true
  delete_on_request: true
  
  # Data minimization
  minimize_logged_data: true  # Only log what's necessary for operation
```

---

## 8. Comprehensive Testing Strategy

### 8.1 Testing Pyramid

```
                    ┌─────────┐
                   │  E2E    │  ~5 tests (full task execution with real providers)
                  ├───────────┤
                 │Integration│  ~50 tests (framework adapters, provider adapters)
                ├─────────────┤
               │   Service   │  ~100 tests (orchestration core, escalation, budget)
              ├───────────────┤
             │    Unit       │  ~300 tests (individual components, pure functions)
            ├─────────────────┤
           │   Property      │  ~50 tests (hypothesis-based invariant testing)
          └───────────────────┘
```

### 8.2 Unit Tests

Test individual components in isolation with mocked dependencies:

```python
# test_cost_tracker.py
def test_cost_calculation_openrouter():
    tracker = CostTracker()
    cost = tracker.calculate_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        model="x-ai/grok-4",
        provider="openrouter"
    )
    assert cost == pytest.approx(0.005, abs=0.0001)

def test_cost_calculation_lmstudio_is_free():
    tracker = CostTracker()
    cost = tracker.calculate_cost(
        prompt_tokens=10000,
        completion_tokens=5000,
        model="local-model",
        provider="lmstudio"
    )
    assert cost == 0.0
```

### 8.3 Property-Based Tests (Hypothesis)

Test invariants that must hold for all inputs:

```python
from hypothesis import given, strategies as st

@given(
    prompt_tokens=st.integers(min_value=0, max_value=1_000_000),
    completion_tokens=st.integers(min_value=0, max_value=1_000_000),
    prompt_price=st.floats(min_value=0, max_value=1.0),
    completion_price=st.floats(min_value=0, max_value=1.0),
)
def test_cost_is_never_negative(prompt_tokens, completion_tokens, prompt_price, completion_price):
    cost = (prompt_tokens / 1_000_000 * prompt_price) + \
           (completion_tokens / 1_000_000 * completion_price)
    assert cost >= 0

@given(
    budget=st.floats(min_value=0.01, max_value=10000),
    spent=st.floats(min_value=0, max_value=20000),
)
def test_budget_never_exceeds_limit(budget, spent):
    enforcer = BudgetEnforcer(limit=budget)
    enforcer._record_spending(spent)
    assert enforcer.remaining >= 0 or enforcer.remaining == -(spent - budget)
```

### 8.4 Service Tests

Test the orchestration core with mock providers:

```python
# test_escalation_engine.py
@pytest.mark.asyncio
async def test_escalation_on_repeated_failure():
    """When all retries fail at L0, escalate to L1."""
    orchestrator = CostOptimizedOrchestrator(
        tiers=make_tiers(),
        budget_daily_usd=100.0,
    )
    
    # Mock L0 to always fail
    orchestrator.providers["lmstudio"].mock_response = MockResponse(
        success=False, error="Context too complex"
    )
    # Mock L1 to succeed
    orchestrator.providers["openrouter"].mock_response = MockResponse(
        success=True, output="def hello(): pass"
    )
    
    result = await orchestrator.execute_task(
        task_id="test-1",
        description="Write a function",
        initial_tier="L0-Coder"
    )
    
    assert result.success is True
    assert result.final_tier == "L1-Coder"
    assert result.total_attempts == 4  # 3 retries at L0 + 1 at L1
```

### 8.5 Integration Tests

Test framework adapters and provider adapters with real (but mocked) dependencies:

```python
# test_crewai_adapter.py
def test_crewai_adapter_wraps_agent():
    """Verify CrewAI adapter produces a cost-aware agent."""
    crew_agent = MockCrewAgent(role="coder")
    orchestrator = CostOptimizedOrchestrator()
    
    wrapped = CrewAIAdapter.wrap_agent(crew_agent, orchestrator)
    
    assert isinstance(wrapped, CostAwareAgent)
    assert wrapped.role == "coder"
    assert wrapped.orchestrator is orchestrator

# test_provider_adapter.py
@pytest.mark.asyncio
async def test_openrouter_adapter_tracks_cost():
    """Verify OpenRouter adapter correctly tracks token usage and cost."""
    adapter = OpenRouterAdapter(api_key="test-key")
    
    result = await adapter.call_completion(
        messages=[{"role": "user", "content": "Say hello"}],
        model="openai/gpt-4o-mini",
    )
    
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.cost_usd > 0
```

### 8.6 End-to-End Tests

Full pipeline tests with real providers (gated by API key availability):

```python
# test_e2e.py
@pytest.mark.e2e
@pytest.mark.requires_api_key
@pytest.mark.asyncio
async def test_full_escalation_pipeline():
    """Execute a real task through the full orchestration pipeline."""
    orchestrator = CostOptimizedOrchestrator(
        config_path="test_config.yaml",
        budget_daily_usd=5.0,
    )
    
    result = await orchestrator.execute_task(
        task_id="e2e-1",
        description="Write a Python function that calculates fibonacci",
        initial_tier="L0-Coder"
    )
    
    assert result.success is True
    assert result.total_cost_usd < 1.0  # Should be cheap
    assert "def fib" in result.output or "def fibonacci" in result.output
```

### 8.7 Chaos Testing

Test resilience under failure conditions:

```python
# test_chaos.py
@pytest.mark.asyncio
async def test_provider_timeout_recovery():
    """When provider times out, circuit breaker should open and recover."""
    orchestrator = make_orchestrator()
    
    # Simulate 10 consecutive timeouts
    orchestrator.providers["openrouter"].mock_behavior = "timeout"
    for _ in range(10):
        with pytest.raises(TimeoutError):
            await orchestrator.execute_task(task_id=f"chaos-{_}", description="test")
    
    # Circuit should be open
    assert orchestrator.circuit_breakers["openrouter"].state == CircuitState.OPEN
    
    # After cooldown, provider recovers
    orchestrator.providers["openrouter"].mock_behavior = "success"
    await asyncio.sleep(61)  # Cooldown period
    
    result = await orchestrator.execute_task(task_id="chaos-recovery", description="test")
    assert result.success is True
```

### 8.8 Load Testing

```python
# test_load.py (using locust or custom async load tester)
async def test_concurrent_executions():
    """Verify system handles 1000 concurrent task executions."""
    orchestrator = CostOptimizedOrchestrator(
        config_path="test_config.yaml",
        budget_daily_usd=1000.0,
    )
    
    tasks = [
        orchestrator.execute_task(
            task_id=f"load-{i}",
            description=f"Task {i}"
        )
        for i in range(1000)
    ]
    
    start = time.monotonic()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.monotonic() - start
    
    successes = sum(1 for r in results if isinstance(r, ExecutionResult) and r.success)
    assert successes >= 950  # 95% success rate under load
    assert duration < 300  # Complete within 5 minutes
```

### 8.9 Test Configuration

```yaml
testing:
  unit:
    framework: "pytest"
    min_coverage: 85
    run_on: "every_commit"
  
  property:
    framework: "hypothesis"
    examples: 100
    run_on: "every_commit"
  
  integration:
    run_on: "pull_request"
    mock_providers: true
  
  e2e:
    run_on: "main_branch_merge"
    requires_api_keys: true
  
  load:
    framework: "locust"
    run_on: "release"
    target_concurrent_users: 1000
  
  chaos:
    framework: "pytest + custom fault injection"
    run_on: "weekly"
```

---

## 9. Simplified Configuration Hierarchy

### 9.1 Problem

The original 6-level configuration hierarchy (architecture:547-553) is too complex and prone to subtle bugs from unexpected overrides.

### 9.2 Decision: 3-Level Hierarchy for v1

```
Level 1: Package defaults (built into code, never changed by user)
Level 2: Project config (./.cost_orchestrator.yaml in project root)
Level 3: Environment variables (COST_ORCH_* overrides)
```

Removed levels:
- ~~Global config (/etc/cost-orchestrator/config.yaml)~~ — Unnecessary for a library
- ~~User config (~/.config/cost-orchestrator/config.yaml)~~ — Confuses project-level vs user-level
- ~~Runtime API overrides~~ — Too dynamic, hard to debug; use env vars instead

### 9.3 Resolution Order

```
1. Package defaults (lowest priority)
2. Project config file (overrides defaults)
3. Environment variables (highest priority)
```

### 9.4 Configuration Loading

```python
class ConfigLoader:
    def load(self, project_path: str | None = None) -> OrchestratorConfig:
        # Level 1: Defaults
        config = DEFAULT_CONFIG.copy()
        
        # Level 2: Project config
        if project_path:
            project_config = self._load_yaml(project_path)
            config = deep_merge(config, project_config)
        else:
            # Auto-discover
            for candidate in ["./.cost_orchestrator.yaml", "./orchestrator.yaml"]:
                if os.path.exists(candidate):
                    config = deep_merge(config, self._load_yaml(candidate))
                    break
        
        # Level 3: Environment variables
        env_config = self._load_env_vars()
        config = deep_merge(config, env_config)
        
        # Validate
        validated = OrchestratorConfig(**config)
        return validated
    
    def _load_env_vars(self) -> dict:
        """Read all COST_ORCH_* environment variables."""
        result = {}
        for key, value in os.environ.items():
            if key.startswith("COST_ORCH_"):
                # COST_ORCH_BUDGET_DAILY_USD=10.0 → {"budget": {"daily_usd": 10.0}}
                path = key.lower().replace("cost_orch_", "").split("_")
                self._set_nested(result, path, self._parse_value(value))
        return result
```

### 9.5 Environment Variable Mapping

```
COST_ORCH_BUDGET_DAILY_USD=10.0       → budget.daily_usd
COST_ORCH_TIERS_L0_CODER_MODEL=qwen   → tiers.L0-Coder.model
COST_ORCH_CIRCUIT_BREAKER_ENABLED=true → circuit_breaker.enabled
COST_ORCH_LOG_LEVEL=DEBUG              → logging.level
```

### 9.6 Configuration Validation

All configuration is validated at startup with clear error messages:

```python
class OrchestratorConfig(BaseModel):
    budget: BudgetConfig
    tiers: dict[str, TierConfig]
    providers: dict[str, ProviderConfig]
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    context_simplification: ContextSimplificationConfig = ContextSimplificationConfig()
    data_retention: DataRetentionConfig = DataRetentionConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
    
    @model_validator(mode='after')
    def validate_tier_chain(self):
        """Ensure fallback chains are valid."""
        for tier_name, tier in self.tiers.items():
            for fallback in tier.fallback_chain:
                if fallback not in self.tiers:
                    raise ValueError(f"Tier '{tier_name}' references unknown fallback tier '{fallback}'")
        return self
    
    @model_validator(mode='after')
    def validate_budget(self):
        """Ensure budget is positive."""
        if self.budget.daily_usd <= 0:
            raise ValueError("Budget daily_usd must be positive")
        return self
```

### 9.7 Minimal Default Configuration

The default config that ships with the package:

```yaml
# Built-in defaults (users only override what they need)
version: "1.0"

budget:
  daily_usd: 10.0
  warning_threshold: 0.8
  failure_mode: "fail_closed"

tiers:
  L0-Coder:
    provider: "lmstudio"
    model: "default"
    max_retries: 3
  L1-Coder:
    provider: "openrouter"
    model: "default"
    max_retries: 3
  L2-Coder:
    provider: "openrouter"
    model: "default"
    max_retries: 2
  L3-Coder:
    provider: "openrouter"
    model: "default"
    max_retries: 1

circuit_breaker:
  enabled: true
  failure_threshold: 0.5
  cooldown_seconds: 60

context_simplification:
  strategy: "section_aware"
  levels: [1.0, 0.7, 0.4]

data_retention:
  log_prompts: false
  log_responses: false
  retention_days:
    execution_metadata: 90
    execution_content: 7

observability:
  opentelemetry:
    enabled: true
    exporters:
      prometheus:
        enabled: true
        port: 9090
```

---

## 10. Summary of Decisions

| Item | Decision | Rationale |
|------|----------|-----------|
| 6. Context simplification | 3-level layered strategy (structural → section-aware → essential-only), no LLM call needed | Deterministic, free, predictable |
| 7. Circuit breaker | Three-state (closed/open/half-open) per provider with configurable thresholds | Prevents wasted spend on degraded providers |
| 8. Budget failure mode | Fail closed by default, configurable to fail_open or fail_open_with_alert | Protects users from unexpected charges |
| 9. Token counting | Provider-delegated (exact) with local fallback (approximate) for pre-call checks | Accurate billing, fast pre-checks |
| 16. Observability | OpenTelemetry as primary standard, Prometheus exporter for compatibility | Industry standard, broad ecosystem support |
| 17. Error classification | 9-category taxonomy with recommended actions per category | Enables intelligent retry vs escalate decisions |
| 18. Data retention | 90-day metadata, 7-day content (opt-in), indefinite aggregated stats | Balances utility with privacy |
| 19. Testing strategy | Pyramid: unit → property → service → integration → E2E → chaos → load | Comprehensive coverage at appropriate levels |
| 20. Config hierarchy | 3 levels: defaults → project file → env vars | Simple, debuggable, no surprise overrides |
