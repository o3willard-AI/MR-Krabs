# Story P2-1: Enhanced CrewAI Integration

**Priority**: P0 (Critical - Blocks P2-2, P2-5)  
**Estimate**: 2 weeks  
**Phase**: Weeks 9-10

---

## User Story

As a CrewAI user  
I want seamless cost tracking and optimization for my CrewAI agents and tools  
So that I can use CrewAI workflows without worrying about AI costs blowing up my budget

---

## Acceptance Criteria

### AC1: CrewAI Tool Integration

- [ ] CrewAI tools automatically show cost in execution logs
- [ ] Tool cost breakdown visible in `orchestrator stats`
- [ ] Tools respect budget limits and warnings
- [ ] No manual configuration needed for CrewAI agents
- [ ] Works with existing CrewAI agent definitions

### AC2: Memory System Compatibility

- [ ] CrewAI memory systems work without cost tracking interference
- [ ] Memory operations don't trigger false budget warnings
- [ ] Context window limits respected across memory operations
- [ ] Memory-heavy workflows tested and verified
- [ ] No performance degradation from memory tracking

### AC3: Advanced Tier Mapping

- [ ] Agent role automatically maps to optimal tier
- [ ] "Researcher" agents use L0/L1 tiers
- [ ] "Planner" agents use L1/L2 tiers
- [ ] "Executor" agents use L2/L3 tiers
- [ ] Override tier mapping configurable per agent

### AC4: Performance Optimization

- [ ] <5% performance overhead on CrewAI workflows
- [ ] No additional network latency introduced
- [ ] Concurrent CrewAI agents work efficiently
- [ ] Cost tracking doesn't block agent execution
- [ ] Benchmarks documented and verified

### AC5: Cost-Aware Tool Execution

- [ ] Tools show cost per execution in logs
- [ ] Tools respect per-task budget limits
- [ ] Tool failures release budget reservations
- [ ] Tool cost summaries in `orchestrator stats`
- [ ] Tools can be cost-disabled if needed

### AC6: CrewAI Workflow Support

- [ ] Multi-agent crews work with cost tracking
- [ ] Sequential workflows properly tracked
- [ ] Hierarchical crews supported
- [ ] Custom workflow definitions compatible
- [ ] CrewAI events logged with cost metadata

---

## Technical Implementation

### Files to Create/Modify

1. `src/integrations/crewai_integration.py` - Enhanced CrewAI adapter
2. `src/integrations/crewai_tools.py` - Cost-aware CrewAI tools
3. `src/core/cost.py` - Extend for CrewAI-specific tracking
4. `docs/user_stories/P2-1_CREWAII_INTEGRATION.md` - This story

### Implementation Plan

```python
# src/integrations/crewai_integration.py

from crewai import Agent, Task, Crew
from src.core.cost import CostTracker, Budget

class CrewAICostIntegrator:
    """Enhanced CrewAI integration with cost tracking."""
    
    def __init__(self, budget: Budget | None = None):
        self.cost_tracker = CostTracker(budget=budget)
        self.agent_tier_mapping = {
            "researcher": ["L0-Coder", "L1-Coder"],
            "planner": ["L1-Coder", "L2-Coder"],
            "executor": ["L2-Coder", "L3-Coder"],
            "critic": ["L1-Coder", "L2-Coder"],
        }
    
    def wrap_agent(self, agent: Agent, tier_override: str | None = None) -> Agent:
        """Wrap a CrewAI agent with cost tracking."""
        
        # Determine tier based on role
        if tier_override:
            tiers = [tier_override]
        else:
            role = agent.role.lower()
            tiers = self.agent_tier_mapping.get(role, ["L0-Coder", "L1-Coder"])
        
        # Create cost-aware agent wrapper
        class CostAwareAgent:
            def __init__(self, agent, tiers, cost_tracker):
                self.agent = agent
                self.tiers = tiers
                self.cost_tracker = cost_tracker
            
            def execute_task(self, task: str, context: dict | None = None) -> dict:
                """Execute task with tiered escalation and cost tracking."""
                for tier in self.tiers:
                    # Reserve budget
                    reservation = self.cost_tracker.reserve_budget(
                        scope=f"crew-{agent.id}-{task[:20]}",
                        estimated_cost=Decimal("0.01")
                    )
                    
                    try:
                        result = self.agent.execute_task(task, context)
                        
                        if result["success"]:
                            # Record cost
                            actual_cost = self.cost_tracker.calculate_cost(...)
                            self.cost_tracker.finalize_spending(reservation.id, actual_cost)
                            return result
                        else:
                            self.cost_tracker.release_reservation(reservation.id)
                    except BudgetExceededError:
                        raise
                
                return {"success": False, "error": "All tiers failed"}
        
        return CostAwareAgent(agent, tiers, self.cost_tracker)
    
    def wrap_tool(self, tool: Tool) -> Tool:
        """Wrap a CrewAI tool to track costs."""
        
        class CostAwareTool:
            def __init__(self, tool, cost_tracker):
                self.tool = tool
                self.cost_tracker = cost_tracker
                self.name = tool.name
            
            def run(self, *args, **kwargs) -> str:
                """Run tool with cost tracking."""
                reservation = self.cost_tracker.reserve_budget(
                    scope=f"tool-{self.name}",
                    estimated_cost=Decimal("0.001")
                )
                
                try:
                    result = self.tool.run(*args, **kwargs)
                    cost = self._estimate_tool_cost(result)
                    self.cost_tracker.finalize_spending(reservation.id, cost)
                    
                    # Log cost
                    print(f"[{self.name}] Cost: ${float(cost):.4f}")
                    return result
                except Exception as e:
                    self.cost_tracker.release_reservation(reservation.id)
                    raise
        
        return CostAwareTool(tool, self.cost_tracker)
    
    def _estimate_tool_cost(self, result: str) -> Decimal:
        """Estimate cost based on tool output."""
        tokens = len(result) // 4  # Rough estimate
        return Decimal(str(tokens * 0.000001))
```

### Integration Examples

```python
# Example 1: Basic CrewAI integration
from crewai import Agent, Task, Crew
from src.integrations.crewai_integration import CrewAICostIntegrator

integrator = CrewAICostIntegrator(budget=Budget(daily_limit_usd=10.0))

# Wrap agents
researcher = integrator.wrap_agent(
    Agent(
        role="Researcher",
        goal="Research topic thoroughly",
        backstory="You are a diligent researcher..."
    )
)

# Wrap tools
file_tool = integrator.wrap_tool(MyCustomTool())

# Create crew
crew = Crew(
    agents=[researcher],
    tasks=[
        Task(
            description="Research AI costs",
            agent=researcher.agent  # Use original agent
        )
    ],
    process=Process.sequential
)

result = crew.kickoff()
print(f"Total cost: ${integrator.cost_tracker.get_daily_total():.2f}")
```

```python
# Example 2: Tier override
integrator.wrap_agent(
    agent=researcher,
    tier_override="L1-Coder"  # Force L1 tier
)
```

```python
# Example 3: Multiple tools
integrator.wrap_tool(web_search_tool)
integrator.wrap_file_tool
integrator.wrap_code_execution_tool
```

---

## Testing Requirements

### Unit Tests (test_crewai_integration.py)

1. `test_wrap_agent_tier_mapping` - Agent role maps to correct tiers
2. `test_wrap_agent_tier_override` - Manual tier override works
3. `test_wrap_tool_cost_tracking` - Tools track costs accurately
4. `test_crew_execution_cost_summary` - Crew execution shows cost summary
5. `test_memory_compatibility` - Memory workflows don't break cost tracking
6. `test_performance_overhead` - <5% overhead verified

### Integration Tests

1. Real CrewAI workflow with multiple agents
2. Tool execution with cost logging
3. Memory operations with cost tracking
4. Budget enforcement across crew execution

---

## Out of Scope

- CrewAI framework changes (this is additive)
- CrewAI CLI integration (handled separately)
- CrewAI dashboard or web UI
- Native CrewAI cost monitoring (external tracking only)

---

## Dependencies

- P1 complete (core cost tracking, budget warnings)
- CrewAI framework accessible for testing
- CrewAI maintainers aware of integration (optional)

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Cost Tracking Overhead** | <5% |
| **Tool Execution Latency** | <10ms added |
| **Memory Operations** | No slowdown |
| **Concurrent Agents** | No degradation |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Performance benchmarks verified
- [ ] Documentation updated
- [ ] Example project included
- [ ] Code reviewed by CrewAI community member (preferred)

---

## Success Metrics

- **Adoption**: 5+ production CrewAI workflows using cost tracking
- **Performance**: <5% overhead verified in benchmarks
- **Community**: Positive feedback from CrewAI users
- **Maintenance**: No breaking changes to CrewAI workflows

---

*Draft: April 26, 2026*
