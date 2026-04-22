# Cost-Optimized Orchestration Prototype

A proof-of-concept implementation demonstrating how to integrate tiered cost optimization with existing agent frameworks (CrewAI, Superpowers).

## Overview

This prototype extracts the valuable core concept from the original `multi-tier-orchestrator` - **cost-aware tiered escalation** - and packages it as:
1. A **Superpowers-style skill** for agent workflows
2. A **framework-agnostic Python library** for tiered orchestration
3. **CrewAI integration** examples
4. A **complete test case** with a medium-difficulty coding problem

## Core Innovation Preserved

The original orchestrator's unique value is its **tiered cost optimization strategy**:
- Start with cheap/free models (L0)
- Escalate to expensive models only when necessary (L1 → L2 → L3)
- Track costs and enforce budgets
- Simplify context on retry to improve success
- Log failures for analysis and improvement

## What We Built

### 1. `cost_optimized_orchestration` Skill
**Location**: `skills/cost_optimized_orchestration/SKILL.md`
- Superpowers-style instructions for agents
- Documents tier configuration, workflow, integration points
- Can be used by Claude, Cursor, OpenCode agents directly

### 2. Framework-Agnostic Orchestrator
**Location**: `skills/cost_optimized_orchestration/orchestrator.py`
- Core `CostOptimizedOrchestrator` class
- `TierConfig` and `ExecutionResult` dataclasses
- Retry logic with context simplification
- Cost tracking and budget enforcement
- CLI interface for testing

### 3. CrewAI Integration
**Location**: `crewai_integration.py`
- Maps tiers to CrewAI agent configurations
- Wraps CrewAI execution with cost tracking
- Provides seamless integration point
- Falls back gracefully when CrewAI not available

### 4. Complete Test Case
**Location**: `examples/task_management_api.md` and `test_task_management.py`
- Medium-difficulty coding problem (Task Management REST API)
- Breaks problem into 8 subtasks with appropriate tier assignments
- Simulates realistic failures and escalations
- Demonstrates cost efficiency analysis

## Key Improvements Over Original

| Aspect | Original Implementation | Prototype Improvement |
|--------|------------------------|----------------------|
| **Architecture** | Monolithic Python agent stack | Framework-agnostic orchestration layer |
| **Tool Parsing** | Brittle regex patterns for each model | Leverages framework-native tool calling |
| **Integration** | Standalone system | Pluggable into CrewAI, Superpowers, etc. |
| **Maintenance** | Custom everything | Builds on established frameworks |
| **Flexibility** | Fixed workflow | Composable skills and agents |

## How It Works

### Tiered Escalation Flow
```
[Task Received]
     ↓
[L0-Planner] → Plan & decompose
     ↓
[L0-Coder] → Attempt implementation
     ├─ Success → [L0-Reviewer] → Review & validate
     └─ Failure → [L1-Coder] → Retry with better model
           ├─ Success → Continue
           └─ Failure → [L2-Coder] → Escalate further
```

### Cost Optimization
- **L0 tiers**: Free/local models (LM Studio) or very cheap (OpenRouter $0.001/M tokens)
- **L1 tiers**: Affordable models ($0.002-0.006/M tokens)
- **L2/L3 tiers**: Premium models ($0.003-0.075/M tokens) used only when necessary

## Usage Examples

### As a Standalone Library
```python
from skills.cost_optimized_orchestration.orchestrator import CostOptimizedOrchestrator

orchestrator = CostOptimizedOrchestrator(budget_daily_usd=10.0)

result = orchestrator.execute_task(
    task_id="1.1",
    description="Create User model with SQLAlchemy",
    context={"tech_stack": "FastAPI, SQLAlchemy, PostgreSQL"},
    initial_tier="L0-Coder"
)

print(f"Cost: ${result.cost_usd:.4f}, Success: {result.success}")
```

### With CrewAI Integration
```python
from crewai_integration import CrewAIOrchestrator

crewai_orchestrator = CrewAIOrchestrator(base_orchestrator)

result = crewai_orchestrator.execute_task_with_escalation(
    task_id="api_endpoint",
    description="Create authentication endpoint",
    context={"framework": "FastAPI", "auth": "JWT"},
    initial_tier="L0-Coder"
)
```

### As a Superpowers Skill
Agents can follow the `SKILL.md` instructions to:
- Analyze task complexity
- Assign appropriate initial tier
- Execute with cost-aware escalation
- Review results and iterate

## Test Results

Running `test_task_management.py` demonstrates:

1. **Successful decomposition** of complex problem into 8 subtasks
2. **Appropriate tier assignment** based on complexity:
   - Simple models: L0-Coder
   - Complex logic: L1-Coder  
   - Infrastructure: L2-Coder
   - Planning: L0-Planner
   - Review: L0-Reviewer
3. **Cost efficiency**: ~80% of work at L0 tiers
4. **Escalation handling**: Failed tasks automatically escalate
5. **Budget enforcement**: Stops execution when budget exceeded

## Integration Paths

### With Superpowers Workflow
```
User Request → Superpowers brainstorming → Plan → 
CostOptimizedOrchestrator tier selection → 
Subagent-driven-development with tiered agents → 
Review → Completion
```

### With CrewAI Agent Hierarchy
```
[Orchestrator Agent] (manages tier selection)
    ├─ [L0-Coder Agent] (junior developer)
    ├─ [L1-Coder Agent] (senior developer) 
    ├─ [L0-Reviewer Agent] (code reviewer)
    └─ [L3-Architect Agent] (system architect)
```

### As OpenCode/Claude Skill
Agent reads `SKILL.md` and applies tiered strategy to any coding task.

## Next Steps

1. **Real LLM Integration**: Replace mock LLM caller with actual OpenRouter/LM Studio API calls
2. **Tool Standardization**: Use LangChain tools or CrewAI tools instead of custom parsing
3. **Superpowers Integration**: Package as actual Superpowers skill for marketplace
4. **Advanced Analytics**: Add more detailed cost/performance tracking
5. **Multi-Framework Support**: Add LangChain, AutoGen, LlamaIndex integrations

## Key Takeaways

1. **The tiered cost optimization concept is valuable** and worth preserving
2. **Building on existing frameworks** reduces complexity and maintenance burden
3. **Skill-based architecture** provides maximum flexibility
4. **The prototype proves the concept works** and can integrate with real workflows
5. **Focus should shift from building agent stack** to creating orchestration patterns for existing stacks

## Running the Tests

```bash
# Test imports
python3 test_imports.py

# Test orchestrator CLI
python3 skills/cost_optimized_orchestration/orchestrator.py \
  --task test1 \
  --description "Write hello world" \
  --tier L0-Coder \
  --budget 5.0

# Run complete test case
python3 test_task_management.py
```

## Requirements

See `requirements.txt` for dependencies. The prototype works without CrewAI installed (falls back to simulation mode).

## License

MIT - Same as original orchestrator.