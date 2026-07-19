# MR-Krabs Improvement Plan — Multi-Phase Roadmap

## What We Know (from 8 hours of adversarial testing)

The loop architecture works. The fixes work. But the final run exposed a
clean dividing line between what's fixed and what's still broken:

| Fixed | Still Broken |
|-------|-------------|
| File extraction filter | QA loop disabled |
| Loop 2 retry on verify failure | Judge feedback contaminates coder prompts |
| Loop 4 static audit (stubs, imports, dead code) | No spec-coverage check |
| Accumulated-files guard clear on retry | L1/L2 OpenCode models echo prompt templates |
| OpenCode+OpenRouter auth | L0-only is still the only reliable tier |
| Connection throttling (.23 crash protection) | Decomposition uses file count, not dependency topology |
| Adaptive chunk sizing (hardware-aware limits) | No post-mortem learning from successes |
| Judge prompt integration checks | get_service_address() still dead code in C3 |

The architecture is correct. The pieces exist. They need wiring, tuning,
and one new component.

---

## Phase 1: Make L1/L2 Reliable (the safety net)

**Problem**: When L0 fails, escalation to L1/L2 produces unpredictable
results — MiMo echoes "COACHING REPLY" templates, DeepSeek sometimes
produces 0 files. The safety net has holes.

**Root cause**: Judge feedback format leaks into coder context. The
judge's coaching reply includes markdown headers and a 5-point structure
that cloud models interpret as their output format.

### 1a. Separate coder feedback from judge output

Currently:
```
Judge produces: "## Coaching Reply\n1. What was done well\n2. What's wrong..."
→ Injected into task_spec
→ Coder sees: "## Coaching Reply" and fills out the template
```

Fix: Strip judge formatting when preparing retry feedback for coders.
Replace the coaching reply with plain fix instructions:

```python
def _format_feedback_for_coder(judge_critique: str, backend: str) -> str:
    """Convert judge coaching reply to coder-friendly fix instructions."""
    if backend == "opencode":
        # OpenCode cloud models are sensitive to prompt format contamination.
        # Strip all markdown headers and coaching structure. Give bare facts.
        return _strip_coaching_format(judge_critique) + "\n\nFix these issues and re-submit ALL files."
    else:
        # PI handles structured feedback fine. Keep the full critique.
        return judge_critique
```

### 1b. Add OpenCode output validation

When OpenCode returns files, validate that they contain actual code (not
template echoes, not empty files, not error messages). If output looks
like a coaching reply, retry with a stripped prompt.

```python
def _is_template_echo(output: str) -> bool:
    """Detect when the model echoed the prompt template instead of writing code."""
    echo_patterns = [
        "COACHING REPLY:",
        "follow the 5-point structure",
        "## Coaching Reply",
        "What was done well",
        "What specific thing is wrong",
    ]
    return any(p in output[:500] for p in echo_patterns)
```

### 1c. L1/L2 should use PI when possible

OpenCode is the bottleneck for L1/L2. The PI adapter works reliably
with local models. For cloud models, PI may also work better than
OpenCode. Test PI with cloud providers as an alternative backend
for L1/L2 tiers.

---

## Phase 2: Enable and Harden Loop 3 (QA)

**Problem**: The verify loop checks "do tests pass?" but not "does the
project actually do what the spec asked?" C2 passed with 2 trivial tests
while missing 6 major requirements. Loop 3 exists (657 lines) but is
disabled.

### 2a. Enable Loop 3 in default config

```yaml
qa:
  enabled: true
  judge_model: judge
  coder_tier: l0-coder
  orchestrator_tier: l0-planner
  timeout: 300
  base_url: "http://127.0.0.1:5000"
```

### 2b. Add spec-coverage scoring

The QA loop generates tests from the spec. After execution, compute a
coverage score: "spec asked for 8 features, behavioral tests verified 2
of them → 25% coverage." Score below threshold (e.g., 70%) is a failure
even if all generated tests pass.

```python
def _compute_spec_coverage(spec: str, test_results: TestSuiteResult) -> float:
    """What fraction of spec requirements have passing behavioral tests?"""
    required = _extract_requirements_from_spec(spec)
    verified = {t.name for t in test_results.passed_tests}
    matched = sum(1 for r in required if any(r.keyword in v for v in verified))
    return matched / len(required) if required else 1.0
```

### 2c. Route QA feedback into decomposition

When Loop 3 finds that chunk A and chunk B have an interface mismatch
(e.g., exported function signature doesn't match what chunk B imports),
feed that back to the decomposer as a rule: "files X and Y must be in
the same chunk."

---

## Phase 3: Spec-Driven Requirement Tracking

**Problem**: Neither the audit nor the judge caught that `get_service_address()`
was dead code in C3. The audit's call-graph check relies on regex-extracting
function names from the spec using specific formatting patterns. If the spec
says "Implement get_service_address(name)" without backticks, it's missed.

### 3a. Structured requirement extraction

Instead of regex-scanning for function names, parse the spec for explicit
requirement markers:

```
## Requirements
- REQ-001: app.py MUST call get_service_address() before connecting to Redis
- REQ-002: registry.py MUST implement POST /register and GET /services/<name>
- REQ-003: gateway.py MUST stream SSE responses without mock data
```

The audit and QA loops can then verify each requirement deterministically.

### 3b. Requirement-aware audit

Extend the audit's call-graph check to use structured requirements when
available, falling back to regex extraction when not:

```python
def check_requirements(files, requirements):
    for req in requirements:
        if req.type == "must_call":
            if not _has_call_site(files, req.function):
                yield Finding(severity="error", message=f"REQ-{req.id}: {req.function}() is never called")
        elif req.type == "must_implement":
            if req.endpoint not in _find_endpoints(files):
                yield Finding(severity="error", message=f"REQ-{req.id}: {req.endpoint} not implemented")
```

---

## Phase 4: Decomposition Optimization

**Problem**: The decomposer chunks by file count. It should chunk by
dependency topology — shared imports together, independent files
parallelized, data models before consumers.

### 4a. Dependency-aware chunking

Before chunking, parse all files for imports and build a dependency
graph. Chunk by connected components, with shared dependencies in
earlier passes:

```python
def chunk_by_dependency_graph(files: list[str], project_root: str) -> list[list[str]]:
    """Group files that share imports together. Put deps before dependents."""
    graph = build_import_graph(files, project_root)
    components = topological_sort(graph)
    # Split large components by adaptive limit
    return split_components(components, compute_adaptive_chunk_limit())
```

### 4b. Post-mortem ordering optimization

After a successful run, analyze which chunking decisions caused retries:

- File X was in chunk 2 but chunk 1 needed it → move X to chunk 1
- Chunk 3 had 7 files but L0 can only handle 4 → split next time
- Files A and B cross-reference each other → put them in the same chunk

Feed these learnings back as decomposition rules.

### 4c. Phase planning

The decomposer should output not just "what goes in each chunk" but
"what ORDER the chunks should run in, and which can run in PARALLEL."
Independent chunks can run concurrently, reducing total wall-clock time.

---

## Phase 5: The Outer Loop's Primary Goal

**Problem**: The outer loop currently activates on failure. Its mature
state should be PROACTIVE — optimizing decomposition so L0 rarely needs
escalation.

### 5a. L0-first decomposition target

The decomposer should target L0's capacity as the PRIMARY constraint:

```
1. Probe L0 context window → N files/pass
2. Analyze spec → M required files
3. If M > N: decompose into M/N chunks, ordered by dependencies
4. If M ≤ N: single pass
5. After each run: if any chunk retried or escalated, adjust N downward
6. After successful run: record the chunking pattern as a rule
```

### 5b. Cost-aware escalation

When L0 fails, the decision to escalate to L1/L2 should factor in cost:

- L0: $0.00 (local GPU, already paid for)
- L1: ~$0.01/request (DeepSeek V4 Flash)
- L2: ~$0.005/request (MiMo v2.5)

If a task has been retried 3 times at L0 and each retry costs nothing,
try more L0 retries with different chunking before escalating to paid
tiers. The default max_retries_per_tier=3 is optimized for cloud costs;
for local L0, raise it to 5-6.

### 5c. Learning transfer between projects

As the pattern library accumulates rules across projects, the
decomposer should apply rules from similar past projects to new ones:

- "All Flask apps need templates/ chunked with their routes"
- "Python packages: __init__.py must be in the same chunk as its submodules"
- "Test files: pair with their source files, don't isolate"

---

## Execution Order

| Phase | What | Effort | Impact | Depends On |
|-------|------|--------|--------|------------|
| **1a** | Separate coder feedback from judge output | Small (~30 lines) | High — fixes L1/L2 contamination | — |
| **1b** | OpenCode output validation | Small (~20 lines) | Medium — catches template echoes | 1a |
| **2a** | Enable Loop 3 in config | Tiny (1 line) | High — activates existing QA | — |
| **2b** | Spec-coverage scoring | Medium (~80 lines) | High — catches C2-style skeletons | 2a |
| **2c** | Route QA feedback into decomposition | Medium (~60 lines) | Medium — improves chunking | 2a, 4a |
| **3a** | Structured requirement extraction | Medium (~100 lines) | Medium — deterministic verification | — |
| **4a** | Dependency-aware chunking | Large (~200 lines) | High — L0 success rate | 3a |
| **4b** | Post-mortem ordering | Medium (~100 lines) | Medium — compounding improvement | 4a |
| **5a** | L0-first decomposition target | Small (~30 lines) | Medium — aligns incentives | 4a |
| **5b** | Cost-aware escalation | Small (~20 lines) | Low — saves pennies | — |
