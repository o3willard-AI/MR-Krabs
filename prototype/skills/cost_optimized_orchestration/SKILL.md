# Cost-Optimized Orchestration Skill

## Purpose
Execute coding tasks with a tiered LLM strategy that optimizes for cost while maintaining quality. Start with cheaper/free models and escalate to more expensive models only when necessary.

## When to Use This Skill
- When given a coding task that requires LLM assistance
- When working within budget constraints
- When you want to maximize efficiency while minimizing cost
- When dealing with complex tasks that may require multiple attempts

## Core Principles
1. **Tiered Escalation**: Start with L0 (cheapest) models, escalate to L1/L2/L3 only on failure
2. **Cost Awareness**: Track token usage and estimate costs for each tier
3. **Context Simplification**: On retry, simplify context to improve success rate
4. **Failure Logging**: Record failures to analyze patterns and improve tier assignments

## Tier Configuration
| Tier | Model | Provider | Cost/Million Tokens | Use Case |
|------|-------|----------|---------------------|----------|
| L0-Planner | qwen/qwen3.5-397b-a17b | OpenRouter | $0.001 | Task planning and decomposition |
| L0-Coder | qwen/qwen3-coder-30b | LM Studio | $0.00 (local) | Initial implementation attempts |
| L0-Reviewer | qwen/qwen3.5-397b-a17b | OpenRouter | $0.001 | Code review and validation |
| L1-Coder | x-ai/grok-4.1-fast | OpenRouter | $0.002/$0.006 | When L0 fails or needs assistance |
| L2-Coder | minimax/minimax-m2.7 | OpenRouter | $0.0002/$0.0006 | Complex logic or bug fixes |
| L3-Coder | anthropic/claude-sonnet-4.6 | OpenRouter | $0.003/$0.015 | Critical or quality-sensitive work |
| L3-Architect | anthropic/claude-opus-4.6 | OpenRouter | $0.015/$0.075 | Architecture decisions and design |

## Workflow

### 1. Task Analysis & Planning (L0-Planner)
- Analyze the problem statement
- Break down into subtasks
- Estimate complexity and assign initial tier
- Create implementation plan

### 2. Initial Implementation (L0-Coder)
- Attempt implementation with local/free model
- If successful: proceed to review
- If failed: log error and escalate to L1

### 3. Code Review (L0-Reviewer)
- Review code against requirements
- Check for bugs, edge cases, best practices
- Provide feedback for improvements

### 4. Escalation Process
For each failed attempt:
1. Log failure with error details
2. Simplify context (remove non-essential information)
3. Retry with same tier (max 3 attempts)
4. If still failing, escalate to next tier

### 5. Cost Tracking
- Estimate tokens for each request
- Calculate cost based on tier pricing
- Enforce budget limits
- Provide cost summary at completion

## Integration Points

### With CrewAI
- Each tier becomes a CrewAI Agent with specific role
- Tasks flow through agent hierarchy
- Handoffs between agents based on success/failure

### With Superpowers Skills
- Use `brainstorming` for initial design
- Use `writing-plans` for task breakdown  
- Use `subagent-driven-development` for execution
- Use `requesting-code-review` for quality checks

### As Standalone
- Can be used as a Python library
- CLI interface for manual execution
- API for integration with other systems

## Implementation Steps

1. **Initialize Orchestrator**
   ```python
   orchestrator = CostOptimizedOrchestrator(
       budget_daily_usd=10.0,
       project_root="."
   )
   ```

2. **Execute Task**
   ```python
   result = orchestrator.execute_task(
       task_id="task_management_api",
       description="Create REST API for task management system",
       context={...}
   )
   ```

3. **Monitor Progress**
   - Check result['success']
   - Review result['attempts']
   - Examine result['cost_usd']
   - View result['output']

4. **Handle Failures**
   ```python
   if not result['success']:
       escalation = orchestrator.escalate_task(
           task_id=result['task_id'],
           next_tier=result['suggested_escalation']
       )
   ```

## Example Usage

```python
# Simple task execution
result = orchestrator.execute_task(
    task_id="1.1",
    description="Create User model with SQLAlchemy",
    context={
        "requirements": "User with id, username, email, hashed_password",
        "tech_stack": "FastAPI, SQLAlchemy, PostgreSQL"
    }
)

print(f"Cost: ${result['cost_usd']:.4f}")
print(f"Tier used: {result['final_tier']}")
print(f"Success: {result['success']}")
```

## Success Metrics
- **Cost Efficiency**: Achieve >80% of tasks at L0/L1 tiers
- **Success Rate**: >90% task completion within 3 attempts
- **Time to Resolution**: Minimize escalations to expensive tiers
- **Budget Adherence**: Stay within daily/monthly budget limits

## Anti-Patterns to Avoid
- ❌ Jumping directly to expensive tiers
- ❌ Not tracking costs and budget
- ❌ Infinite retries without escalation
- ❌ Ignoring failure patterns
- ❌ Not simplifying context on retry