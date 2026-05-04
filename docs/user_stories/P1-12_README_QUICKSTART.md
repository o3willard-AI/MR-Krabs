# Story P1-12: README with Quickstart

**Priority**: P1 (High)  
**Estimate**: 1 day  
**Phase**: Week 7-8

---

## User Story

As a new developer  
I want a clear README with working examples  
So that I can get started in <15 minutes

---

## Acceptance Criteria

### AC1: README Structure
- [ ] **Quickstart Section**: 3-4 code blocks showing basic usage
- [ ] **Installation**: `pip install cost-orchestrator`
- [ ] **Configuration**: Set `OPENROUTER_API_KEY`
- [ ] **First Task**: `from cost_orchestrator import ask; result = ask("task")`
- [ ] **Before/After**: Show cost savings example
- [ ] **CLI Examples**: All commands with output
- [ ] **API Reference**: `ask()` function signature
- [ ] **Troubleshooting**: Common issues and fixes
- [ ] **FAQ**: Frequently asked questions
- [ ] **Contributing**: How to contribute

### AC2: Quickstart Examples
```python
# Example 1: Simple API
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")
print(result.output)
print(f"Cost: ${result.cost:.4f}")
print(f"Tier used: {result.tier_used}")

# Example 2: With custom budget
result = ask("Build a REST API", budget=5.0)

# Example 3: CLI
$ orchestrator run --tier cheap --description "Hello world"
```

### AC3: Cost Savings Demo
- [ ] Show before/after comparison
- [ ] Before: GPT-4o always = $0.12/task
- [ ] After: 87% cheap, 13% expensive = $0.015/task avg
- [ ] 87% cost reduction claim

### AC4: CLI Examples
- [ ] `orchestrator init` - setup
- [ ] `orchestrator doctor` - health check
- [ ] `orchestrator run` - execute
- [ ] `orchestrator dry-run` - estimate cost
- [ ] `orchestrator explain` - view history
- [ ] `orchestrator stats` - cost summary

### AC5: Troubleshooting Section
- [ ] "API key not working" - check env var
- [ ] "Budget exceeded" - increase budget or break task
- [ ] "LM Studio connection failed" - check URL
- [ ] "Task keeps escalating" - task may be too complex
- [ ] "Config file not found" - run `orchestrator init`

---

## Technical Implementation

### Files to Create/Modify
1. `README.md` - Rewrite with new structure

### Content Outline

```markdown
# Cost-Optimized AI Orchestrator

Quick start. Installation. Usage examples. Before/After cost comparison.
CLI commands. API reference. Troubleshooting. FAQ. Contributing. License.
```

---

## Testing Requirements

### Verification
- [ ] All code examples work
- [ ] CLI examples produce expected output
- [ ] Links all work
- [ ] No dead references

---

## Out of Scope
- API documentation site (Phase 2)
- Translation (Phase 2)
- Video tutorials (Phase 3)

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] All examples tested
- [ ] New developer can onboard in <15 minutes
- [ ] Code reviewed and approved
