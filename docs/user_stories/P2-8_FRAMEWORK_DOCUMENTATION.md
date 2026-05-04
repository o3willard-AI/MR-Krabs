# Story P2-8: Framework Documentation & Examples

**Priority**: P2 (Medium - Improves Adoption)  
**Estimate**: 1 week  
**Phase**: Week 16c

---

## User Story

As a new developer  
I want comprehensive documentation and working examples for all supported frameworks  
So that I can quickly integrate cost tracking into my existing projects

---

## Acceptance Criteria

### AC1: Framework-Specific Guides

- [ ] CrewAI integration guide (10+ pages)
- [ ] LangChain integration guide (10+ pages)
- [ ] Quick-start guides for each framework
- [ ] Troubleshooting sections per framework
- [ ] FAQ per framework

### AC2: Working Examples

- [ ] 5+ production-ready example projects
- [ ] Each example fully documented
- [ ] Examples tested and verified
- [ ] Examples include all cost features
- [ ] Examples follow framework best practices

### AC3: Tutorial Content

- [ ] Step-by-step tutorial for new framework users
- [ ] Tutorial covers setup to production
- [ ] Tutorial includes cost optimization tips
- [ ] Tutorial verified by external developer
- [ ] Tutorial <2 hours to complete

### AC4: Migration Guides

- [ ] Guide: No cost tracking → Cost tracking
- [ ] Guide: v1 config → v2 config
- [ ] Guide: Single framework → Multi-framework
- [ ] Migration checklists provided
- [ ] Common pitfalls documented

### AC5: API Reference

- [ ] Complete API documentation
- [ ] Code examples for all functions
- [ ] Parameter descriptions
- [ ] Return value documentation
- [ ] Error handling documentation

### AC6: Community Resources

- [ ] Contributing guidelines
- [ ] Code of conduct
- [ ] Issue templates
- [ ] Discussion templates
- [ ] Example contribution guide

---

## Technical Implementation

### Files to Create/Modify

1. `docs/frameworks/crewai.md` - CrewAI integration guide
2. `docs/frameworks/langchain.md` - LangChain integration guide
3. `docs/examples/` - Example projects
4. `docs/tutorials/` - Tutorials
5. `docs/api/` - API reference
6. `CONTRIBUTING.md` - Contributing guide

### Documentation Structure

```
docs/
├── frameworks/
│   ├── crewai.md          # CrewAI integration guide
│   ├── langchain.md       # LangChain integration guide
│   └── comparison.md      # Framework comparison
├── examples/
│   ├── crewai_cost_tracking/
│   │   ├── README.md
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── README.md
│   ├── langchain_cost_tracking/
│   ├── multi_framework/
│   ├── batch_processing/
│   └── real_time_monitoring/
├── tutorials/
│   ├── getting_started.md
│   ├── advanced_features.md
│   ├── production_ready.md
│   └── troubleshooting.md
├── api/
│   ├── index.md
│   ├── cost.md
│   ├── orchestrator.md
│   └── integrations.md
├── CONTRIBUTING.md
└── MIGRATION.md
```

### Implementation Plan

```markdown
# docs/frameworks/crewai.md

# CrewAI Integration Guide

## Overview

This guide shows how to integrate cost tracking into your CrewAI projects.

## Prerequisites

- CrewAI installed (`pip install crewai`)
- MR-Krabs installed (`pip install cost-orchestrator`)
- API key configured

## Quick Start

```python
from crewai import Agent, Task, Crew
from src.integrations.crewai_integration import CrewAICostIntegrator

# Initialize cost integrator
integrator = CrewAICostIntegrator(
    budget=Budget(daily_limit_usd=10.0)
)

# Wrap your agents
researcher = integrator.wrap_agent(
    Agent(
        role="Researcher",
        goal="Research the topic thoroughly",
        backstory="You are a diligent researcher..."
    )
)

# Wrap your tools
web_search = integrator.wrap_tool(
    WebSearchTool()
)

# Create crew
crew = Crew(
    agents=[researcher],
    tasks=[
        Task(
            description="Research AI costs",
            agent=researcher.agent,
            tools=[web_search]
        )
    ],
    process=Process.sequential
)

# Run
result = crew.kickoff()

# Check costs
print(f"Total cost: ${integrator.cost_tracker.get_daily_total():.2f}")
```

## Advanced Configuration

### Custom Tier Mapping

```python
integrator = CrewAICostIntegrator()

# Override tier mapping for specific agent
integrator.agent_tier_mapping["senior_researcher"] = ["L2-Coder", "L3-Coder"]
```

### Tool Cost Configuration

```python
# Disable cost tracking for expensive tool
web_search = integrator.wrap_tool(
    WebSearchTool(),
    track_costs=False
)
```

### Memory Integration

```python
# CrewAI memory works seamlessly with cost tracking
from crewai.memory import LongTermMemory

# Memory operations are tracked but don't trigger false warnings
integrator.wrap_agent(agent_with_memory)
```

## Best Practices

### 1. Start with L0

```python
# Let the agent choose its tier
researcher = integrator.wrap_agent(
    Agent(role="Researcher", ...)
)
# Defaults to L0-Coder or L1-Coder
```

### 2. Monitor Costs

```python
# After crew execution
stats = orchestrator.get_analytics_summary()
print(f"Success rate: {stats.overall_success_rate:.1f}%")
print(f"Tier breakdown: {stats.tier_analytics}")
```

### 3. Optimize Tier Assignments

```python
# Based on analytics, adjust tier mappings
if researcher_analytics.avg_success_rate > 95:
    integrator.agent_tier_mapping["researcher"] = ["L0-Coder"]
```

## Troubleshooting

### "Costs seem too high"

**Check:**
- Are you wrapping all tools?
- Is memory causing false costs?
- Are you tracking tool calls correctly?

**Fix:**
```python
# Disable tracking for expensive operations
integrator.wrap_tool(expensive_tool, track_costs=False)
```

### "Agents not escalating"

**Check:**
- Is `max_attempts` set high enough?
- Are errors being caught?
- Is budget limiting escalation?

**Fix:**
```python
# Increase retry attempts
result = agent.execute_task(task, max_attempts=5)
```

## API Reference

### `CrewAICostIntegrator`

#### `__init__(budget)`

Initialize cost integrator.

**Parameters:**
- `budget`: Budget object (optional)

#### `wrap_agent(agent, tier_override=None)`

Wrap agent with cost tracking.

**Parameters:**
- `agent`: CrewAI Agent instance
- `tier_override`: Force specific tier (optional)

**Returns:**
- `CostAwareAgent` wrapper

#### `wrap_tool(tool, track_costs=True)`

Wrap tool with cost tracking.

**Parameters:**
- `tool`: CrewAI Tool instance
- `track_costs`: Enable/disable tracking

**Returns:**
- `CostAwareTool` wrapper

## Examples

See `examples/crewai_cost_tracking/` for complete working example.

## Related

- [Main Documentation](../README.md)
- [Cost Tracking API](../api/cost.md)
- [Troubleshooting Guide](../tutorials/troubleshooting.md)
"""
```

### Example Project Structure

```
examples/crewai_cost_tracking/
├── README.md                 # Example overview
├── main.py                   # Working example
├── requirements.txt          # Dependencies
├── .env.example             # Environment template
├── config.toml              # Cost config
└── outputs/                 # Example outputs
    ├── task1_result.txt
    └── task2_result.txt
```

**Example README:**

```markdown
# CrewAI Cost Tracking Example

## Overview

This example demonstrates how to use MR-Krabs with CrewAI for cost-optimized agent workflows.

## What You'll Learn

- How to wrap CrewAI agents with cost tracking
- How to track tool costs
- How to view cost analytics
- How to optimize tier assignments

## Setup

```bash
pip install crewai cost-orchestrator
export OPENROUTER_API_KEY="your-key"
```

## Run the Example

```bash
python main.py
```

## Expected Output

```
[Researcher] Starting task...
[Researcher] Cost: $0.0012 (L0-Coder)
[Researcher] Task succeeded in 1 attempt
[Researcher] Total cost: $0.0012

[Analyst] Starting task...
[Analyst] Cost: $0.0008 (L1-Coder)
[Analyst] Task succeeded in 2 attempts
[Analyst] Total cost: $0.0020

Cost Summary:
  Total: $0.0020
  L0-Coder: $0.0012 (60%)
  L1-Coder: $0.0008 (40%)
  Success Rate: 100%
```

## Cost Savings

Compared to always using GPT-4o:
- This example: $0.0020
- GPT-4o only: $0.24
- **Savings: 99.2%**

## Next Steps

- Try with your own CrewAI agents
- Explore the analytics features
- Read the [CrewAI Integration Guide](../../docs/frameworks/crewai.md)

## Questions?

Open an issue on GitHub!
"""

---

## Testing Requirements

### Documentation Tests

1. All code examples runnable and verified
2. All links work (no dead links)
3. All examples tested with current code
4. All tutorials verified by external developer
5. All API documentation accurate

### Integration Tests

1. Example projects run end-to-end
2. Documentation builds without errors
3. Examples produce expected outputs
4. All cost tracking features demonstrated

---

## Out of Scope

- Video tutorials (Phase 3)
- Interactive tutorials (Phase 3)
- Multi-language documentation (Phase 3)
- Professional graphics (Phase 3)
- Translation (Phase 3)

---

## Dependencies

- P2-1 through P2-7 complete (for comprehensive docs)
- All features working and tested

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Documentation Quality** | >95% accuracy |
| **Example Success Rate** | 100% |
| **Tutorial Completion** | <2 hours |
| **Readability** | >4/5 rating |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] All examples tested and verified
- [ ] External developer verified tutorials
- [ ] All links work
- [ ] API documentation accurate
- [ ] Contributing guidelines clear
- [ ] Code of conduct included
- [ ] Documentation review complete

---

## Success Metrics

- **Adoption**: 20+ developers using examples
- **Documentation Quality**: >4.5/5 rating
- **Tutorial Success**: 90%+ completion rate
- **Community Contributions**: 5+ PRs from docs

---

*Draft: April 26, 2026*
