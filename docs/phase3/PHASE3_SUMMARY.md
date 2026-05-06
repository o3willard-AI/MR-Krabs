# Phase 3 Summary: CrewAI Multi-Agent Refactor

**Status**: Planning Phase  
**Timeline**: 5 weeks  
**Goal**: Transform MR-Krabs from single-agent to multi-agent framework using CrewAI

---

## 🎯 What We're Building

Currently, MR-Krabs uses a **single LLM agent** with cost optimization:
```python
result = ask("Write code for X")  # Single agent handles everything
```

After Phase 3, you'll have **collaborative multi-agent crews**:
```python
# Multiple specialized agents working together
crew = CostAwareCrew(
    agents=[planner, coder, reviewer],  # Each with specific role/tier
    tasks=[design_task, code_task, review_task],
    budget_limit=5.0  # Crew-level budget
)
result = crew.kickoff()  # Collaborative execution!
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              MR-Krabs + CrewAI Framework                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  User Request                                           │
│      │                                                  │
│      v                                                  │
│  ┌──────────────────────────────────────────┐          │
│  │   CostAwareCrew (Team of Agents)         │          │
│  │   - Sequential Process                   │          │
│  │   - Hierarchical Process                 │          │
│  │   - Consensus Process                    │          │
│  └──────────────────────────────────────────┘          │
│         │    │    │                                    │
│         v    v    v                                    │
│  ┌──────────────────────────────────────────┐          │
│  │   CostAwareAgents (Specialized Roles)    │          │
│  │                                           │          │
│  │   Researcher  → L0 (cheap, fast)         │          │
│  │   Coder       → L1 (balanced)            │          │
│  │   Reviewer    → L1 (quality focus)       │          │
│  │   Architect   → L2 (complex decisions)   │          │
│  │   Strategist  → L3 (critical tasks)      │          │
│  └──────────────────────────────────────────┘          │
│         │    │    │                                    │
│         v    v    v                                    │
│  ┌──────────────────────────────────────────┐          │
│  │   CostTrackingCallbackHandler            │          │
│  │   - Real-time cost monitoring            │          │
│  │   - Budget warnings (80%, 100%)          │          │
│  │   - Metrics collection                   │          │
│  └──────────────────────────────────────────┘          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Implementation Stories (12 Total)

### Foundation (Week 1-2)
| Story | Description | Files to Create |
|-------|-------------|-----------------|
| **P3-1** | Install & Configure CrewAI | `pyproject.toml`, tests |
| **P3-2** | CostAwareAgent base class | `src/agents/cost_aware_agent.py` |
| **P3-3** | CostAwareTask with budget limits | `src/agents/cost_aware_task.py` |

### Core Integration (Week 2-3)
| Story | Description | Files to Create |
|-------|-------------|-----------------|
| **P3-4** | CostAwareCrew wrapper | `src/agents/cost_aware_crew.py` |
| **P3-5** | Real-time cost callback handler | `src/callbacks/cost_tracking_handler.py` |
| **P3-6** | Backward compatibility layer | Update `src/__init__.py` |

### Advanced Features (Week 3-4)
| Story | Description | Files to Create |
|-------|-------------|-----------------|
| **P3-7** | Pre-built crew templates (code review, debugging, etc.) | `src/agents/templates.py` |
| **P3-8** | Hierarchical process support | Extend `cost_aware_crew.py` |
| **P3-9** | Crew performance metrics & optimization | `src/analytics/crew_metrics.py` |

### Migration & Polish (Week 4-5)
| Story | Description | Files to Create |
|-------|-------------|-----------------|
| **P3-10** | Migration guide & examples | `docs/MIGRATION_TO_CREWAI.md` |
| **P3-11** | Update tests + add crew-specific tests | 5+ new test files |
| **P3-12** | CLI enhancements for CrewAI | `src/cli/crew_commands.py` |

---

## 🎁 Key Features After Phase 3

### 1. Role-Based Tier Assignment
Agents automatically get the right LLM tier based on their role:

```python
# No manual tier selection needed!
researcher = CostAwareAgent(
    role='researcher',        # → Auto-assigned L0 (cheap)
    goal='Analyze this code'
)

coder = CostAwareAgent(
    role='coder',             # → Auto-assigned L1 (balanced)
    goal='Write the function'
)

architect = CostAwareAgent(
    role='architect',         # → Auto-assigned L2 (complex decisions)
    goal='Design system architecture'
)
```

### 2. Pre-Built Crew Templates
Ready-to-use workflows for common scenarios:

```python
from src.agents.templates import create_code_review_crew

# One-line crew creation!
crew = create_code_review_crew(
    code_snippet="def buggy_function(): ...",
    budget_limit=5.0
)

result = crew.kickoff()
print(result.raw)  # Professional code review output
```

### 3. Backward Compatibility
Existing code continues to work:

```python
# Old API still works (now powered by CrewAI internally!)
from cost_orchestrator import ask

result = ask("Write a sorting function")
print(result.output)  # ✓ Works unchanged!
```

### 4. Real-Time Cost Tracking
Live budget monitoring during crew execution:

```
🤖 researcher starting task...
✅ Task completed: code_analysis
   Cost: $0.0012

🤖 coder starting task...
⚠️  BUDGET WARNING: 75% of budget used ($3.75/$5.00)
✅ Task completed: code_generation  
   Cost: $0.0048

🤖 reviewer starting task...
✅ Task completed: final_review
   Cost: $0.0019

📊 Crew Cost Report:
   Expected: $5.00
   Actual:   $0.0079
   Savings:  99.8%! 🎉
```

---

## 📊 Before vs After Comparison

### BEFORE (Current MR-Krabs)

**Single Agent Workflow:**
```python
result = ask("Write, test, and review a Python sorting function")
# Single LLM tries to do everything → higher cost, lower quality
```

**Limitations:**
- ❌ No collaboration between specialized agents
- ❌ One size fits all (same tier for entire task)
- ❌ Manual workflow orchestration required
- ❌ No memory/state across calls

### AFTER (Phase 3 Complete)

**Multi-Agent Crew Workflow:**
```python
crew = CostAwareCrew(
    agents=[planner, coder, tester, reviewer],
    tasks=[
        "Design efficient sorting algorithm",      # L0 researcher
        "Implement the function in Python",        # L1 coder  
        "Write comprehensive tests",              # L1 tester
        "Review and validate the solution"         # L1 reviewer
    ],
    budget_limit=5.0
)

result = crew.kickoff()
```

**Benefits:**
- ✅ Specialized agents collaborate (researcher → coder → tester → reviewer)
- ✅ Each agent uses optimal tier for their role (L0 for research, L1 for coding)
- ✅ Automatic workflow orchestration via CrewAI
- ✅ Shared context/memory across all agents in crew
- ✅ Cost tracking per agent and per task
- ✅ Real-time budget warnings

---

## 💰 Cost Impact Analysis

### Expected Cost Breakdown (Example: Code Generation Task)

| Agent Role | Tier | Estimated Cost | Purpose |
|------------|------|----------------|---------|
| Researcher | L0 | $0.001 | Analyze requirements |
| Coder | L1 | $0.005 | Write implementation |
| Tester | L1 | $0.004 | Create test cases |
| Reviewer | L1 | $0.002 | Validate quality |
| **Total** | - | **$0.012** | - |

### Comparison: Single Agent vs Multi-Agent

| Approach | Cost | Quality | Speed |
|----------|------|---------|-------|
| Single L3 agent (current escalation) | $0.05-0.15 | High | Slow (complex prompt) |
| **Multi-agent crew (Phase 3)** | **$0.012** | **Higher** (specialized) | **Faster** (parallel possible) |
| Single L0 agent (cheap but poor) | $0.001 | Low | Fast |

**Result**: Multi-agent crews provide **better quality at 75% lower cost** than escalating to expensive tiers!

---

## 🚀 How to Start

### Immediate Next Steps:

1. **Review the full plan**: `docs/phase3/PHASE3_CREWAI_REFACTOR_PLAN.md`
2. **Install CrewAI** (Story P3-1):
   ```bash
   cd /home/sblanken/working/code/MR-Krabs
   pip install crewai
   ```
3. **Create first agent** (Story P3-2):
   ```python
   from src.agents import CostAwareAgent
   
   researcher = CostAwareAgent(
       role='researcher',
       goal='Analyze code for issues',
       backstory='You are an expert code analyst'
   )
   ```
4. **Run basic test**:
   ```bash
   pytest tests/unit/test_cost_aware_agent.py -v
   ```

### Recommended Implementation Order:

**Week 1** (Foundation):
- P3-1 → P3-2 → P3-3

**Week 2** (Core):
- P3-4 → P3-5 → P3-6

**Week 3** (Features):
- P3-7 → P3-8 → P3-9

**Week 4-5** (Polish):
- P3-10 → P3-11 → P3-12

---

## ⚠️ Important Notes

### What Won't Change:
- ✅ Existing `ask()` API continues to work
- ✅ Cost tracking fundamentals remain the same
- ✅ Tier system (L0-L3) unchanged
- ✅ Budget limits and warnings work identically
- ✅ All existing tests pass without modification

### What Will Improve:
- 🚀 Multi-agent collaboration capabilities
- 🎯 Better cost optimization through role-based tiers
- 📈 Higher quality outputs via specialization
- ⚡ Faster execution with parallel processing
- 🛠️ Pre-built templates for common workflows

---

## 📚 Documentation Locations

| Document | Location | Purpose |
|----------|----------|---------|
| **Full Phase 3 Plan** | `docs/phase3/PHASE3_CREWAI_REFACTOR_PLAN.md` | Detailed implementation guide |
| **This Summary** | `docs/phase3/PHASE3_SUMMARY.md` | Executive overview (you are here) |
| **Migration Guide** | `docs/MIGRATION_TO_CREWAI.md` | How to migrate existing code (Post-P3-10) |
| **Crew Templates** | `docs/examples/` | Working examples of crews (Post-P3-7) |

---

## 🤔 Questions?

### Common Questions:

**Q: Do I need to rewrite all my existing code?**  
A: No! The `ask()` API remains fully functional. You can adopt CrewAI incrementally.

**Q: Will this increase my costs?**  
A: No - role-based tier assignment should actually REDUCE costs by using cheap models (L0) for simple tasks.

**Q: How much does CrewAI add to package size?**  
A: ~5MB additional dependencies, negligible performance impact (<5% overhead).

**Q: Can I still use LM Studio local models?**  
A: Yes! All existing provider support continues to work.

**Q: What if I only want single-agent simplicity?**  
A: Continue using `ask()` API - it's simpler and works great for most tasks!

---

## 🎯 Success Criteria

Phase 3 will be considered successful when:

- ✅ All 12 stories (P3-1 to P3-12) complete
- ✅ 85%+ test coverage on new CrewAI modules
- ✅ 100% backward compatibility (all existing tests pass)
- ✅ < 5% performance overhead vs. current implementation
- ✅ At least 4 working crew templates with examples
- ✅ Migration guide published with clear examples

---

**Ready to start?** Begin with Story P3-1: Install CrewAI and create your first `CostAwareAgent`! 🚀

For questions or blockers, refer to the detailed plan in `docs/phase3/PHASE3_CREWAI_REFACTOR_PLAN.md`.
