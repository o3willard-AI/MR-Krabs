# Phase 3: CrewAI Multi-Agent Framework Refactor

**Status**: Planning  
**Date**: May 5, 2026  
**Author**: MR-Krabs Team  
**Priority**: P0 - Fundamental Architecture Change

---

## Executive Summary

This document outlines the comprehensive plan to refactor MR-Krabs from a single-agent cost-optimized orchestrator into a **CrewAI-based multi-agent framework**. This fundamental architectural shift will enable:

1. **True collaborative intelligence** - Multiple specialized agents working together
2. **Role-based tier assignment** - Automatic model selection based on agent role (researcher→L0, coder→L1, architect→L2/3)
3. **Task decomposition** - Complex workflows automatically broken into subtasks across agents
4. **Enhanced cost optimization** - Fine-grained cost tracking per agent/task interaction
5. **Production-ready workflows** - Sequential, hierarchical, and autonomous execution modes

---

## Current Architecture Analysis

### Existing Components (Pre-CrewAI)

```
┌─────────────────────────────────────┐
│   ask() API                         │
│   - Single entry point              │
│   - Cost tracking built-in          │
└──────────┬──────────────────────────┘
           │
           v
┌─────────────────────────────────────┐
│   LLMOrchestrator                   │
│   - 4-tier escalation (L0-L3)       │
│   - Retry with context simplification│
│   - Tool execution (file_read/write)│
└──────────┬──────────────────────────┘
           │
           v
┌─────────────────────────────────────┐
│   Provider Adapters                 │
│   - OpenRouter                      │
│   - LM Studio                       │
└─────────────────────────────────────┘
```

### Limitations of Current Design

1. **No collaboration** - Single agent handles entire task
2. **Manual workflow definition** - Users must orchestrate multi-step tasks
3. **Limited specialization** - All agents use same tier selection logic
4. **No memory/state management** - Each call is independent
5. **Rigid escalation** - Linear L0→L1→L2→L3 only

---

## Target Architecture: CrewAI Integration

### High-Level Design

```
┌──────────────────────────────────────────────┐
│   MR-Krabs CrewAI Framework                  │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │   CostAwareCrew (extends Crew)         │ │
│  │   - Budget tracking per crew execution │ │
│  │   - Automatic tier adjustment          │ │
│  │   - Cost-based task routing            │ │
│  └────────────────────────────────────────┘ │
│              │                              │
│              v                              │
│  ┌────────────────────────────────────────┐ │
│  │   CostAwareAgent (extends Agent)       │ │
│  │   - Role-based tier assignment         │ │
│  │   - Individual cost tracking           │ │
│  │   - Budget-constrained tool calls      │ │
│  └────────────────────────────────────────┘ │
│              │                              │
│              v                              │
│  ┌────────────────────────────────────────┐ │
│  │   CostAwareTask (extends Task)         │ │
│  │   - Per-task budget limits             │ │
│  │   - Escalation on cost overrun         │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │   CostTrackingCallbackHandler          │ │
│  │   - Real-time cost monitoring          │ │
│  │   - Budget warnings/alerts             │ │
│  │   - Metrics collection                 │ │
│  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Agent Role → Tier Mapping (Default)

| Agent Role Category | Examples | Default Tier | Cost/Million Tokens | When to Use |
|---------------------|----------|--------------|---------------------|-------------|
| **Research/Planning** | researcher, analyst, planner | L0 | $0.001-0.004 | Fast iteration, low stakes |
| **Development** | coder, developer, engineer | L1 | $0.004-0.008 | Code generation, moderate complexity |
| **Review/Quality** | reviewer, validator, tester | L1 | $0.004-0.008 | Code review, validation tasks |
| **Architecture/Design** | architect, designer, lead | L2 | $0.008-0.015 | System design, complex decisions |
| **Strategy/Critical** | strategist, consultant, expert | L3 | $0.015-0.075 | High-stakes, critical path tasks |

### Crew Types

1. **SequentialCrew** - Tasks executed in order (default)
2. **HierarchicalCrew** - Manager agent delegates to workers
3. **ConsensusCrew** - Multiple agents vote on outputs
4. **AutonomousCrew** - Agents self-organize based on goals

---

## Implementation Plan

### Phase 3.1: Foundation (Week 1-2)

#### Story P3-1: Install & Configure CrewAI
**Goal**: Add CrewAI as dependency and configure base integration

**Tasks**:
- [ ] Add `crewai` to `pyproject.toml` dependencies
- [ ] Create compatibility layer for existing `ask()` API
- [ ] Set up environment variables (`CREWAI_API_KEY` optional, use existing `OPENROUTER_API_KEY`)
- [ ] Write basic "hello crew" test script

**Acceptance Criteria**:
```bash
# Install CrewAI
pip install crewai

# Basic test passes
python -c "from crewai import Agent, Task, Crew; print('✓ CrewAI imported')"
```

**Files to Modify**:
- `pyproject.toml` - Add dependency
- `tests/unit/test_crewai_basic.py` - New test file

---

#### Story P3-2: CostAwareAgent Base Class
**Goal**: Create enhanced Agent class with cost tracking

**Tasks**:
- [ ] Create `src/agents/cost_aware_agent.py`
- [ ] Implement role-to-tier mapping logic
- [ ] Add cost estimation before LLM calls
- [ ] Integrate with existing `CostTracker`
- [ ] Add budget warning callbacks

**Pseudocode**:
```python
class CostAwareAgent(Agent):
    def __init__(self, role: str, goal: str, backstory: str, 
                 tier_override: TierLevel = None, **kwargs):
        # Determine tier from role
        self.tier_level = self._map_role_to_tier(role) or tier_override
        self.tier = TierManager.get_tier(self.tier_level)
        
        # Configure LLM with cost-aware settings
        llm_config = {
            'model': self.tier.model,
            'temperature': self.tier.temperature,
            'base_url': self.tier.base_url,
        }
        
        super().__init__(role=role, goal=goal, backstory=backstory, 
                        llm=llm_config, **kwargs)
        
        # Initialize cost tracking
        self.cost_tracker = CostTracker.get_global()
        self.total_cost = 0.0
        
    def _map_role_to_tier(self, role: str) -> TierLevel:
        role_map = DEFAULT_ROLE_TO_TIER_MAPPING
        return role_map.get(role.lower(), TierLevel.L0)
    
    async def execute_task(self, task: Task) -> str:
        # Pre-call cost estimation
        estimated_cost = self.estimate_cost(task.description)
        
        if estimated_cost > self.budget_limit:
            raise BudgetExceededError(...)
        
        # Execute with tracking
        result = await super().execute_task(task)
        
        # Post-call cost recording
        actual_cost = self.calculate_actual_cost(result)
        self.cost_tracker.record(
            task_id=task.name,
            agent_role=self.role,
            tier=self.tier.name,
            cost=actual_cost
        )
        
        return result
```

**Acceptance Criteria**:
- Agent automatically selects correct tier based on role
- Cost tracked per agent execution
- Budget warnings triggered at 80% and 100% thresholds
- Existing tests pass with new agent class

**Files to Create**:
- `src/agents/__init__.py`
- `src/agents/cost_aware_agent.py`
- `tests/unit/test_cost_aware_agent.py`

---

#### Story P3-3: CostAwareTask with Budget Limits
**Goal**: Add budget constraints and escalation to tasks

**Tasks**:
- [ ] Create `src/agents/cost_aware_task.py`
- [ ] Implement per-task budget limits
- [ ] Add automatic escalation logic (L0→L1→L2 if cost exceeds threshold)
- [ ] Integrate with CrewAI task execution hooks

**Pseudocode**:
```python
class CostAwareTask(Task):
    def __init__(self, description: str, expected_output: str,
                 agent: CostAwareAgent, budget_limit: float = 1.0,
                 escalation_enabled: bool = True, **kwargs):
        self.budget_limit = budget_limit
        self.escalation_enabled = escalation_enabled
        self.current_cost = 0.0
        
        super().__init__(description=description, 
                        expected_output=expected_output,
                        agent=agent, **kwargs)
    
    def on_start(self):
        """Called before task execution"""
        self.cost_tracker = CostTracker.get_global()
        self.reservation = self.cost_tracker.reserve_budget(
            scope=self.name,
            estimated_cost=self.budget_limit
        )
        
    def on_end(self, output: str):
        """Called after task completion"""
        actual_cost = self.calculate_cost(output)
        
        if actual_cost > self.budget_limit and self.escalation_enabled:
            # Escalate to next tier
            self.agent.tier_level = TierManager.next_tier(self.agent.tier_level)
            return self.execute()  # Retry with upgraded tier
        
        # Finalize cost tracking
        self.cost_tracker.finalize_spending(self.reservation.id, actual_cost)
        
    def on_error(self, error: Exception):
        """Called on task failure"""
        self.cost_tracker.release_reservation(self.reservation.id)
        raise error
```

**Acceptance Criteria**:
- Tasks respect individual budget limits
- Automatic escalation when budget exceeded
- Cost released on task failure
- Integration with CrewAI lifecycle hooks

**Files to Create**:
- `src/agents/cost_aware_task.py`
- `tests/unit/test_cost_aware_task.py`

---

### Phase 3.2: Core Integration (Week 2-3)

#### Story P3-4: CostAwareCrew Base Class
**Goal**: Create Crew wrapper with team-level cost tracking

**Tasks**:
- [ ] Create `src/agents/cost_aware_crew.py`
- [ ] Implement crew-level budget management
- [ ] Add cost-based process selection (sequential vs hierarchical)
- [ ] Integrate metrics collection for crew performance

**Key Features**:
```python
class CostAwareCrew(Crew):
    def __init__(self, agents: List[CostAwareAgent], 
                 tasks: List[CostAwareTask],
                 budget_limit: float = 10.0,
                 process: Process = Process.sequential,
                 **kwargs):
        self.budget_limit = budget_limit
        self.process = process
        
        # Calculate expected crew cost
        self.expected_cost = sum(task.budget_limit for task in tasks)
        
        if self.expected_cost > self.budget_limit:
            print(f"⚠️  Warning: Expected cost (${self.expected_cost:.2f}) "
                  f"exceeds budget limit (${budget_limit:.2f})")
        
        super().__init__(agents=agents, tasks=tasks, process=process, **kwargs)
    
    def kickoff(self) -> CrewOutput:
        """Start crew execution with cost monitoring"""
        # Pre-execution budget check
        remaining_budget = self.cost_tracker.get_remaining()
        
        if remaining_budget < self.expected_cost * 0.8:
            print(f"⚠️  Low budget warning: Only ${remaining_budget:.2f} remaining")
            
        # Execute with cost tracking
        result = super().kickoff()
        
        # Post-execution reporting
        actual_cost = self.calculate_total_cost()
        print(f"\n📊 Crew Cost Report:")
        print(f"   Expected: ${self.expected_cost:.2f}")
        print(f"   Actual:   ${actual_cost:.2f}")
        print(f"   Savings:  {(1 - actual_cost/self.expected_cost)*100:.1f}%")
        
        return result
```

**Acceptance Criteria**:
- Crew-level budget tracking works
- Cost warnings displayed before execution
- Post-execution cost reports generated
- Supports sequential, hierarchical, and consensus processes

**Files to Create**:
- `src/agents/cost_aware_crew.py`
- `tests/unit/test_cost_aware_crew.py`

---

#### Story P3-5: CostTrackingCallbackHandler
**Goal**: Real-time cost monitoring during crew execution

**Tasks**:
- [ ] Create `src/callbacks/cost_tracking_handler.py`
- [ ] Implement CrewAI callback handler interface
- [ ] Add real-time budget warnings
- [ ] Integrate with existing metrics system

**Implementation**:
```python
class CostTrackingCallbackHandler(BaseCallbackHandler):
    """CrewAI callback handler for real-time cost tracking."""
    
    def __init__(self, budget_limit: float = 10.0, 
                 warning_threshold: float = 0.8):
        self.budget_limit = budget_limit
        self.warning_threshold = warning_threshold
        self.current_cost = 0.0
        self.warnings_triggered = set()
        
    def on_agent_start(self, agent: Agent, **kwargs) -> None:
        """Called when agent starts executing"""
        print(f"🤖 {agent.role} starting task...")
        
    def on_agent_end(self, agent: Agent, output: str, **kwargs) -> None:
        """Called when agent finishes execution"""
        cost = self.estimate_cost(output)
        self.current_cost += cost
        
        # Check budget threshold
        budget_used_pct = self.current_cost / self.budget_limit
        
        if budget_used_pct >= self.warning_threshold:
            warning_key = f"{int(budget_used_pct * 100)}%"
            
            if warning_key not in self.warnings_triggered:
                print(f"🚨 BUDGET ALERT: {int(budget_used_pct * 100)}% "
                      f"of budget used (${self.current_cost:.2f}/{self.budget_limit:.2f})")
                self.warnings_triggered.add(warning_key)
                
        # Record in global tracker
        CostTracker.get_global().record(
            task_id=f"{agent.role}_execution",
            tier=agent.metadata.get('tier', 'L0'),
            cost=cost
        )
        
    def on_task_start(self, task: Task, **kwargs) -> None:
        """Called when task starts"""
        print(f"📝 Starting task: {task.name}")
        
    def on_task_end(self, task: Task, output: TaskOutput, **kwargs) -> None:
        """Called when task completes"""
        print(f"✅ Task completed: {task.name}")
        print(f"   Cost: ${output.cost_estimate:.4f}")
```

**Acceptance Criteria**:
- Real-time cost updates during execution
- Budget warnings at configurable thresholds
- Integration with existing `CostTracker`
- Non-blocking (doesn't slow down execution)

**Files to Create**:
- `src/callbacks/__init__.py`
- `src/callbacks/cost_tracking_handler.py`
- `tests/unit/test_cost_callback_handler.py`

---

#### Story P3-6: Backward Compatibility Layer
**Goal**: Maintain existing `ask()` API while adding CrewAI support

**Tasks**:
- [ ] Update `src/__init__.py` to support both APIs
- [ ] Create wrapper that converts `ask()` calls to single-agent crews
- [ ] Ensure all existing tests pass unchanged
- [ ] Document migration path for users

**Implementation**:
```python
# src/__init__.py - Backward compatible ask() API

def ask(
    prompt: str,
    system_prompt: str = None,
    tier: str = None,
    max_cost: float = None,
    auto_escalate: bool = True,
) -> AskResult:
    """
    Execute a prompt with cost optimization.
    
    BACKWARD COMPATIBLE: This API remains unchanged but now uses CrewAI internally.
    For multi-agent workflows, use CostAwareCrew directly.
    """
    # Create single-agent crew for backward compatibility
    from src.agents import CostAwareAgent, CostAwareTask, CostAwareCrew
    
    # Determine agent role from tier
    if tier:
        agent_tier = TierLevel[tier.replace('-Coder', '').replace('-Planner', '')]
        agent_role = 'coder'  # Default role for ask()
    else:
        agent_role = 'researcher'  # Cheap by default
    
    # Create agent
    agent = CostAwareAgent(
        role=agent_role,
        goal="Answer user queries accurately and efficiently",
        backstory="You are a cost-optimized AI assistant",
        tier_override=agent_tier if tier else None
    )
    
    # Create task
    task = CostAwareTask(
        description=prompt,
        expected_output="A helpful response to the user's query",
        agent=agent,
        budget_limit=max_cost or 1.0
    )
    
    # Execute crew
    crew = CostAwareCrew(
        agents=[agent],
        tasks=[task],
        budget_limit=max_cost or 10.0,
        process=Process.sequential
    )
    
    result = crew.kickoff()
    
    # Convert CrewOutput to AskResult for compatibility
    return AskResult(
        output=result.raw,
        cost=result.cost_estimate,
        tier=agent.tier.name,
        model=agent.tier.model,
        success=True,
        duration_seconds=result.duration,
        attempts=1,
        tokens=result.tokens
    )
```

**Acceptance Criteria**:
- All existing tests pass without modification
- `ask()` API works identically to before
- Internal implementation uses CrewAI
- Performance degradation < 5%

**Files to Modify**:
- `src/__init__.py` - Add CrewAI wrapper
- `tests/unit/test_init.py` - Verify backward compatibility

---

### Phase 3.3: Advanced Features (Week 3-4)

#### Story P3-7: Pre-built Crew Templates
**Goal**: Provide ready-to-use crew configurations for common scenarios

**Templates to Implement**:

1. **CodeReviewCrew** - Automated code review workflow
   ```python
   def create_code_review_crew(code_snippet: str) -> CostAwareCrew:
       """Create a crew for code review with researcher, coder, and reviewer."""
       
       researcher = CostAwareAgent(
           role='researcher',
           goal='Analyze code for issues and improvements',
           backstory='You are an expert code analyzer'
       )
       
       coder = CostAwareAgent(
           role='coder',
           goal='Generate improved versions of the code',
           backstory='You are a skilled software developer'
       )
       
       reviewer = CostAwareAgent(
           role='reviewer',
           goal='Validate improvements and provide final recommendations',
           backstory='You are a senior code reviewer'
       )
       
       tasks = [
           CostAwareTask(
               description=f"Analyze this code: {code_snippet}",
               expected_output="List of issues and potential improvements",
               agent=researcher
           ),
           CostAwareTask(
               description="Generate improved code based on analysis",
               expected_output="Improved code snippet",
               agent=coder
           ),
           CostAwareTask(
               description="Review the improved code and provide final feedback",
               expected_output="Final review with recommendations",
               agent=reviewer
           )
       ]
       
       return CostAwareCrew(
           agents=[researcher, coder, reviewer],
           tasks=tasks,
           process=Process.sequential,
           budget_limit=5.0
       )
   ```

2. **CodeGenerationCrew** - Full-stack code generation
3. **ResearchCrew** - Multi-source research and synthesis
4. **DebuggingCrew** - Bug detection and fixing workflow

**Acceptance Criteria**:
- At least 4 pre-built crew templates
- Each template has working example in `docs/examples/`
- Templates use appropriate tier assignments
- Cost estimates provided for each template

**Files to Create**:
- `src/agents/templates.py`
- `docs/examples/code_review_crew.py`
- `docs/examples/code_generation_crew.py`
- `tests/unit/test_crew_templates.py`

---

#### Story P3-8: Hierarchical Process Support
**Goal**: Enable manager-worker crew architectures for complex tasks

**Tasks**:
- [ ] Implement `Process.hierarchical` support with cost awareness
- [ ] Add manager agent tier upgrade (typically L2 or L3)
- [ ] Implement cost-aware task delegation
- [ ] Add performance comparisons (sequential vs hierarchical)

**Key Considerations**:
- Manager agents should use higher tiers (L2/L3) for decision-making
- Worker agents can use lower tiers (L0/L1) for execution
- Total crew cost includes manager overhead
- Hierarchical better for complex, multi-dependency tasks

**Acceptance Criteria**:
- Hierarchical crews execute correctly
- Manager tier automatically upgraded
- Cost tracking works across delegation chains
- Performance benchmarks included in tests

**Files to Modify**:
- `src/agents/cost_aware_crew.py` - Add hierarchical support
- `tests/unit/test_hierarchical_crew.py` - New test file

---

#### Story P3-9: Crew Performance Metrics & Optimization
**Goal**: Track and optimize crew execution costs over time

**Tasks**:
- [ ] Extend `src/core/analytics.py` for crew metrics
- [ ] Add crew performance dashboard (CLI)
- [ ] Implement automatic tier optimization suggestions
- [ ] Create cost comparison reports (before/after CrewAI)

**Metrics to Track**:
```python
class CrewMetrics:
    """Performance metrics for crew executions."""
    
    def __init__(self):
        self.total_executions = 0
        self.total_cost = 0.0
        self.avg_cost_per_crew = 0.0
        self.cost_by_tier = defaultdict(float)
        self.cost_by_role = defaultdict(float)
        self.success_rate = 0.0
        self.avg_duration = 0.0
        
    def record_crew_execution(self, crew: CostAwareCrew, 
                             output: CrewOutput, success: bool):
        """Record metrics from crew execution."""
        self.total_executions += 1
        self.total_cost += output.total_cost
        
        # Per-tier breakdown
        for agent in crew.agents:
            self.cost_by_tier[agent.tier.name] += agent.total_cost
            self.cost_by_role[agent.role] += agent.total_cost
            
        # Update averages
        self.avg_cost_per_crew = self.total_cost / self.total_executions
        
    def get_optimization_suggestions(self) -> List[str]:
        """Generate cost optimization recommendations."""
        suggestions = []
        
        # Suggestion 1: Downgrade expensive roles if possible
        for role, cost in self.cost_by_role.items():
            if cost > self.avg_cost_per_crew * 0.5:
                suggestions.append(
                    f"⚠️  Role '{role}' costs ${cost:.2f} (>{self.avg_cost_per_crew*0.5:.2f}). "
                    f"Consider using lower tier or simplifying tasks."
                )
                
        # Suggestion 2: Identify underutilized expensive tiers
        for tier, cost in self.cost_by_tier.items():
            if 'L3' in tier and cost < self.total_cost * 0.1:
                suggestions.append(
                    f"💡 Tier '{tier}' underutilized (${cost:.2f}). "
                    f"Review if L3 is necessary for assigned tasks."
                )
                
        return suggestions
```

**Acceptance Criteria**:
- Crew metrics dashboard command added (`cost-orchestrator crew-metrics`)
- Optimization suggestions generated automatically
- Cost comparison reports available (JSON/CSV export)
- Integration with existing analytics system

**Files to Create**:
- `src/analytics/crew_metrics.py`
- `src/cli/crew_commands.py`
- `tests/unit/test_crew_metrics.py`

---

### Phase 3.4: Migration & Documentation (Week 4-5)

#### Story P3-10: Migration Guide & Examples
**Goal**: Help users migrate from `ask()` API to CrewAI workflows

**Documentation to Create**:
1. **Migration Guide** - Step-by-step migration path
2. **CrewAI Quickstart** - Getting started with multi-agent workflows
3. **Best Practices** - When to use single-agent vs multi-agent
4. **Cost Optimization Tips** - Maximizing savings with CrewAI

**Migration Example**:
```python
# BEFORE: Single ask() call
from cost_orchestrator import ask

result = ask("Write a Python function that sorts a list")
print(result.output)

# AFTER: Multi-agent crew for complex tasks
from src.agents import CostAwareAgent, CostAwareTask, CostAwareCrew

# Define specialized agents
planner = CostAwareAgent(
    role='planner',
    goal='Design efficient sorting algorithms',
    backstory='You are an algorithm expert'
)

coder = CostAwareAgent(
    role='coder',
    goal='Implement sorting functions in Python',
    backstory='You are a Python developer'
)

tester = CostAwareAgent(
    role='tester',
    goal='Validate sorting function correctness',
    backstory='You are a QA engineer'
)

# Define tasks
tasks = [
    CostAwareTask(
        description="Design an efficient sorting algorithm",
        expected_output="Algorithm design with complexity analysis",
        agent=planner
    ),
    CostAwareTask(
        description="Implement the sorting function in Python",
        expected_output="Working Python code",
        agent=coder
    ),
    CostAwareTask(
        description="Test the implementation with edge cases",
        expected_output="Test results and validation",
        agent=tester
    )
]

# Execute crew
crew = CostAwareCrew(
    agents=[planner, coder, tester],
    tasks=tasks,
    process=Process.sequential
)

result = crew.kickoff()
print(result.raw)
```

**Acceptance Criteria**:
- Migration guide covers all use cases
- At least 5 working examples in `docs/examples/`
- Cost comparison shown (before/after CrewAI)
- Video tutorial or animated GIF demonstrating workflow

**Files to Create**:
- `docs/MIGRATION_TO_CREWAI.md`
- `docs/examples/migration_examples/` (directory with multiple examples)
- `README.md` - Update with CrewAI section

---

#### Story P3-11: Update Existing Tests & Add Crew-Specific Tests
**Goal**: Ensure 85%+ test coverage for new CrewAI components

**Test Categories**:
1. **Unit Tests** - Individual agent/task/crew components
2. **Integration Tests** - Full crew execution workflows
3. **Cost Tracking Tests** - Verify cost accounting accuracy
4. **Performance Tests** - Benchmark execution time and cost
5. **Backward Compatibility Tests** - Ensure `ask()` still works

**Test Coverage Targets**:
| Module | Target Coverage | Current (Pre-CrewAI) |
|--------|----------------|---------------------|
| `cost_aware_agent.py` | 90% | N/A |
| `cost_aware_task.py` | 85% | N/A |
| `cost_aware_crew.py` | 85% | N/A |
| `cost_tracking_handler.py` | 90% | N/A |
| Crew templates | 80% | N/A |
| Backward compatibility | 100% | 74% |

**Acceptance Criteria**:
- All new modules meet coverage targets
- Existing tests pass without modification
- Performance degradation < 5%
- Test suite completes in < 2 minutes

**Files to Create**:
- `tests/unit/test_cost_aware_agent.py`
- `tests/unit/test_cost_aware_task.py`
- `tests/unit/test_cost_aware_crew.py`
- `tests/integration/test_crew_workflows.py`
- `tests/performance/test_crew_benchmarks.py`

---

#### Story P3-12: CLI Enhancements for CrewAI
**Goal**: Add CrewAI-specific CLI commands and improve UX

**New Commands**:
```bash
# List available crew templates
cost-orchestrator crews list

# Create a crew from template
cost-orchestrator create code-review --input file.py

# Execute custom crew definition
cost-orchestrator run-crew --config crew_config.yaml

# View crew execution history
cost-orchestrator crew-history --limit 10

# Analyze crew costs
cost-orchestrator crew-costs --by-role
```

**Implementation**:
```python
# src/cli/crew_commands.py

@cli.group()
def crews():
    """Manage CrewAI workflows."""
    pass

@crews.command()
def list():
    """List available crew templates."""
    templates = [
        ("code-review", "Automated code review with researcher + coder + reviewer"),
        ("code-generation", "Full-stack code generation workflow"),
        ("research", "Multi-source research and synthesis"),
        ("debugging", "Bug detection and fixing workflow")
    ]
    
    print("\nAvailable Crew Templates:\n")
    for name, description in templates:
        print(f"  {name:20s} - {description}")
    print()

@crews.command()
@click.argument('template')
@click.option('--input', '-i', help='Input file or text')
@click.option('--budget', '-b', default=5.0, help='Budget limit in USD')
def create(template: str, input: str, budget: float):
    """Create and execute a crew from template."""
    from src.agents.templates import get_crew_template
    
    crew = get_crew_template(template, input_data=input, budget_limit=budget)
    result = crew.kickoff()
    
    print(f"\n✅ Crew executed successfully!")
    print(f"Output: {result.raw[:200]}...")  # Preview
    print(f"Total Cost: ${result.total_cost:.4f}")
```

**Acceptance Criteria**:
- All new commands documented in CLI help
- Interactive templates with sensible defaults
- Cost estimates shown before execution
- Error handling with clear messages

**Files to Create/Modify**:
- `src/cli/crew_commands.py` (new)
- `src/cli/main.py` - Add crews command group
- `tests/unit/test_crew_cli_commands.py` (new)

---

## Risk Assessment & Mitigation

### Technical Risks

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|-----------|--------|---------------------|
| CrewAI API changes break integration | Medium | High | Abstract CrewAI calls behind interface; use semantic versioning |
| Performance degradation with CrewAI overhead | Medium | Medium | Benchmark before/after; optimize callback handlers |
| Cost tracking accuracy issues | Low | High | Extensive unit tests; validate against known costs |
| Backward compatibility broken | Low | Critical | Maintain `ask()` API; comprehensive regression tests |

### Mitigation Strategies

1. **Incremental Rollout** - Deploy CrewAI features behind feature flags initially
2. **Dual Mode Support** - Run both old and new systems in parallel during transition
3. **Extensive Testing** - 85%+ coverage target for all new modules
4. **Monitoring & Alerts** - Real-time cost tracking with anomaly detection
5. **Rollback Plan** - Quick revert to pre-CrewAI version if critical issues found

---

## Success Metrics

### Technical Metrics

- ✅ **Test Coverage**: 85%+ on all new CrewAI modules
- ✅ **Backward Compatibility**: 100% of existing tests pass
- ✅ **Performance**: < 5% overhead compared to direct LLM calls
- ✅ **Cost Accuracy**: Within 10% of actual API billing

### Business Metrics

- ✅ **Cost Savings**: Maintain 87% average savings (same as pre-CrewAI)
- ✅ **User Adoption**: > 50% of users adopt CrewAI workflows within 3 months
- ✅ **Developer Experience**: Reduced complexity for multi-step tasks (measured via user feedback)

### Quality Metrics

- ✅ **Zero Critical Bugs**: No production-cost-affecting bugs in first release
- ✅ **Documentation Coverage**: 100% of public API documented with examples
- ✅ **Community Feedback**: > 4.0/5.0 average rating from early adopters

---

## Timeline & Milestones

### Week 1-2: Foundation (P3-1 to P3-3)
- ✅ CrewAI installed and configured
- ✅ `CostAwareAgent` base class working
- ✅ `CostAwareTask` with budget limits functional

**Deliverables**:
- Core agent/task classes
- Basic unit tests passing
- Developer documentation draft

### Week 2-3: Core Integration (P3-4 to P3-6)
- ✅ `CostAwareCrew` wrapper complete
- ✅ Callback handler for real-time tracking
- ✅ Backward compatibility layer working

**Deliverables**:
- Full CrewAI integration
- Existing tests pass unchanged
- Performance benchmarks established

### Week 3-4: Advanced Features (P3-7 to P3-9)
- ✅ Pre-built crew templates available
- ✅ Hierarchical process support
- ✅ Crew metrics and optimization dashboard

**Deliverables**:
- 4+ crew templates with examples
- CLI commands for crew management
- Analytics dashboard functional

### Week 4-5: Migration & Polish (P3-10 to P3-12)
- ✅ Migration guide published
- ✅ Documentation complete
- ✅ Test coverage targets met

**Deliverables**:
- Complete migration documentation
- 85%+ test coverage achieved
- Ready for beta release

---

## Conclusion

This Phase 3 refactor represents a fundamental architectural evolution from single-agent cost optimization to **collaborative multi-agent intelligence**. By leveraging CrewAI's proven framework while maintaining MR-Krabs' core cost-tracking capabilities, we enable:

1. **True collaborative workflows** - Multiple specialized agents working together
2. **Role-based cost optimization** - Automatic tier selection based on agent responsibility
3. **Production-ready patterns** - Sequential, hierarchical, and consensus execution modes
4. **Backward compatibility** - Existing `ask()` API continues to work seamlessly

**Next Steps**:
1. Review this plan with the team
2. Create GitHub issues for each story (P3-1 through P3-12)
3. Begin implementation with P3-1 (CrewAI installation & configuration)
4. Establish weekly milestone reviews to track progress

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Agent** | Autonomous AI entity with a specific role and goal |
| **Task** | Unit of work assigned to an agent |
| **Crew** | Collection of agents working together to complete tasks |
| **Tier** | Cost/performance level (L0-L3) determining which LLM model to use |
| **Process** | Execution strategy (sequential, hierarchical, consensus) |
| **Callback Handler** | Hook into CrewAI execution lifecycle for custom logic |

---

## Appendix B: Reference Links

- CrewAI Documentation: https://docs.crewai.com
- CrewAI GitHub: https://github.com/crewAIInc/crewAI
- MR-Krabs Repository: https://github.com/pairadmin/MR-Krabs
- Cost Optimization Guide: `docs/COST_OPTIMIZED_ORCHESTRATION_SUMMARY.md`

---

**Document Version**: 1.0  
**Last Updated**: May 5, 2026  
**Review Date**: Weekly during Phase 3 implementation
