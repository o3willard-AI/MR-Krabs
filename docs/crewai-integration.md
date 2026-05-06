# CrewAI Integration Guide

**MR-Krabs Version 0.2.0+** includes built-in CrewAI multi-agent support for complex AI workflows.

---

## Overview

CrewAI is a powerful framework for orchestrating autonomous AI agents that work together to complete complex tasks. MR-Krabs integrates CrewAI as a **required dependency**, meaning it's automatically installed when you install our package.

### Why CrewAI?

- **Multi-Agent Workflows**: Coordinate multiple specialized AI agents working on different aspects of a task
- **Process Templates**: Sequential, hierarchical, and custom execution patterns
- **Built-in Tool Support**: Agents can use tools (search, code execution, API calls)
- **Memory & Context**: CrewAI manages conversation history and context sharing between agents
- **Enterprise Ready**: Production-grade framework used by many companies

### MR-Krabs Enhancements

On top of CrewAI, we add:

- ✅ **Cost Tracking**: Monitor token usage across all agents in real-time
- ✅ **Budget Enforcement**: Set spending limits per task or entire crew
- ✅ **Auto-Escalation**: Automatically use better models when cheap ones fail
- ✅ **Metrics & Export**: Track crew performance and export cost reports

---

## Installation

CrewAI is automatically installed with MR-Krabs:

```bash
pip install cost-orchestrator
# CrewAI + all dependencies installed automatically!
```

### Verifying Installation

```bash
python -c "from crewai import Agent, Task, Crew; print('✅ CrewAI ready!')"
```

---

## Quick Start

### 1. Basic Example

```python
from cost_orchestrator import CostAwareAgent, CostAwareTask, CostAwareCrew

# Define your agents
researcher = CostAwareAgent(
    role="Research Lead",
    goal="Conduct comprehensive research on AI trends",
    backstory="Expert researcher with 10+ years in AI/ML",
)

writer = CostAwareAgent(
    role="Content Writer", 
    goal="Write engaging technical articles",
    backstory="Skilled technical writer specializing in AI topics",
)

# Define your tasks
research_task = CostAwareTask(
    description="Research the latest trends in LLM cost optimization",
    expected_output="Detailed research report with key findings",
    agent=researcher,
    cost_limit=0.50,  # $0.50 max for this task
)

writing_task = CostAwareTask(
    description="Write a blog article based on the research",
    expected_output="Complete article ready for publication",
    agent=writer,
    cost_limit=0.75,  # $0.75 max for this task
)

# Create and run the crew
crew = CostAwareCrew(
    tasks=[research_task, writing_task],
    agents=[researcher, writer],
    cost_limit=1.25,  # Total budget: $1.25
)

result = crew.kickoff()
print(result["output"])
```

### 2. Using the Convenience Function

For quick prototypes, use `create_simple_crew()`:

```python
from cost_orchestrator import create_simple_crew

crew = create_simple_crew(
    tasks=[
        {
            "description": "Analyze customer feedback data",
            "expected_output": "Analysis with key insights",
            "agent_role": 0,  # Use first agent
        },
        {
            "description": "Write executive summary",
            "expected_output": "Executive summary document",
            "agent_role": 1,  # Use second agent
        },
    ],
    agents=[
        {"role": "Data Analyst", "goal": "Analyze customer data"},
        {"role": "Business Writer", "goal": "Write executive reports"},
    ],
    process="sequential",
)

result = crew.kickoff()
```

---

## Core Concepts

### Agents

Agents are the workers in your crew. Each has:

- **Role**: What they are (e.g., "Researcher", "Developer")
- **Goal**: What they should accomplish
- **Backstory**: Context that shapes their behavior
- **LLM Config**: Which model to use (affects cost and quality)

```python
agent = CostAwareAgent(
    role="Senior Python Developer",
    goal="Write production-ready Python code",
    backstory="Expert Python developer with focus on clean, efficient code",
    llm_config={"model": "google/gemma-7b-it"},  # Budget-friendly option
)
```

### Tasks

Tasks define what work needs to be done:

- **Description**: Detailed task instructions
- **Expected Output**: What the result should look like
- **Agent**: Which agent performs this task
- **Cost Limit**: Maximum budget for this task (optional)

```python
task = CostAwareTask(
    description="Implement a REST API endpoint for user registration",
    expected_output="Working Python code with FastAPI, including validation and error handling",
    agent=developer_agent,
    cost_limit=1.00,  # $1 max budget
)
```

### Crews

A crew orchestrates multiple agents and tasks:

- **Tasks**: List of tasks to complete
- **Agents**: Pool of available agents
- **Process**: Execution pattern (sequential, hierarchical, etc.)
- **Cost Limit**: Total budget for the entire crew

```python
crew = CostAwareCrew(
    tasks=[task1, task2, task3],
    agents=[agent1, agent2],
    config=CrewConfig(process="hierarchical"),  # Manager coordinates work
    cost_limit=5.00,  # $5 total budget
)
```

---

## Process Types

### Sequential (Default)

Tasks execute one after another in order:

```python
crew = CostAwareCrew(
    tasks=[task1, task2, task3],
    agents=[agent1, agent2],
    config=CrewConfig(process="sequential"),
)
```

**Best for**: Linear workflows where each step depends on the previous one.

### Hierarchical

CrewAI appoints a manager agent to coordinate work:

```python
crew = CostAwareCrew(
    tasks=[task1, task2, task3],
    agents=[agent1, agent2, agent3],  # Manager + workers
    config=CrewConfig(process="hierarchical"),
)
```

**Best for**: Complex workflows requiring coordination and delegation.

### Other Processes

CrewAI supports additional patterns:

- `hierarchical`: Manager coordinates tasks
- `sequential`: Default, linear execution
- Custom processes available in future CrewAI versions

---

## Cost Management

### Setting Budgets

```python
# Per-task budget
task = CostAwareTask(
    description="...",
    expected_output="...",
    agent=my_agent,
    cost_limit=0.50  # $0.50 max for this task
)

# Total crew budget
crew = CostAwareCrew(
    tasks=[task1, task2],
    agents=[agent1, agent2],
    cost_limit=1.50  # $1.50 total (includes buffer for overhead)
)
```

### Budget Strategy

**Recommended**: Set crew budget to sum of task budgets + 20% buffer:

```python
task_budget = sum(task.cost_limit or 0 for task in tasks)
crew_budget = task_budget * 1.2  # Add 20% buffer
```

### Cost-Efficient Models

Use budget-friendly models for cost-sensitive agents:

```python
# Cheap models (good for simple tasks)
budget_agent = CostAwareAgent(
    role="Data Processor",
    goal="Process and format data",
    llm_config={"model": "google/gemma-2b-it"},  # ~$0.10/1M tokens
)

# Better models (for complex reasoning)
expert_agent = CostAwareAgent(
    role="Senior Architect",
    goal="Design system architecture",
    llm_config={"model": "anthropic/claude-3-haiku"},  # ~$2.50/1M tokens
)
```

---

## Advanced Usage

### Adding Tools to Agents

CrewAI agents can use tools (search, code execution, APIs):

```python
from crewai_tools import SerperDevTool, CodeInterpreterTool

# Add search capability
search_agent = CostAwareAgent(
    role="Researcher",
    goal="Conduct online research",
    tools=[SerperDevTool()],  # Search engine tool
)

# Add code execution
coder_agent = CostAwareAgent(
    role="Developer",
    goal="Write and test code",
    tools=[CodeInterpreterTool()],  # Python interpreter
)
```

### Multiple Crew Runs

Run the same crew with different inputs:

```python
crew = create_simple_crew(tasks, agents)

inputs = [
    {"topic": "AI in healthcare"},
    {"topic": "Blockchain applications"},
    {"topic": "Quantum computing"},
]

results = crew.kickoff_for_each(inputs)
```

### Error Handling

```python
try:
    result = crew.kickoff()
except Exception as e:
    print(f"Crew execution failed: {e}")
    # Fallback logic here
```

---

## Best Practices

### 1. Use Appropriate Models

Match model capability to task complexity:

- **Simple tasks** → `google/gemma-2b-it` (cheapest)
- **Medium complexity** → `google/gemma-7b-it`, `microsoft/phi-3`
- **Complex reasoning** → `anthropic/claude-3-haiku`, `openai/gpt-4o-mini`

### 2. Set Realistic Budgets

Start with generous budgets, then optimize:

```python
# Phase 1: Debug with high budget
crew = CostAwareCrew(..., cost_limit=10.0)

# Phase 2: Optimize after testing
crew = CostAwareCrew(..., cost_limit=3.0)
```

### 3. Be Specific in Descriptions

Vague tasks = wasted tokens + poor results:

```python
# ❌ Bad
task = CostAwareTask(
    description="Write something about AI",
    expected_output="Output",
    agent=writer,
)

# ✅ Good
task = CostAwareTask(
    description=(
        "Write a 500-word blog introduction about AI cost optimization. "
        "Focus on multi-tier LLM strategies. Target audience: technical "
        "founders. Tone: professional but accessible."
    ),
    expected_output="500-word blog introduction paragraph",
    agent=writer,
)
```

### 4. Test Incrementally

Start small, then scale:

```python
# Test with one task first
test_crew = CostAwareCrew(
    tasks=[task1],
    agents=[agent1],
)

# Then add more
full_crew = CostAwareCrew(
    tasks=[task1, task2, task3],
    agents=[agent1, agent2, agent3],
)
```

---

## Troubleshooting

### Common Issues

#### "CrewAI not installed"

```bash
pip install crewai
# Or reinstall MR-Krabs (includes CrewAI automatically)
pip install --upgrade cost-orchestrator
```

#### Budget exceeded

Increase budget or use cheaper models:

```python
agent = CostAwareAgent(
    role="...",
    llm_config={"model": "google/gemma-2b-it"},  # Cheaper alternative
)

crew = CostAwareCrew(..., cost_limit=5.0)  # Increase from $3 to $5
```

#### Poor output quality

Try better models or more specific instructions:

```python
agent = CostAwareAgent(
    role="...",
    llm_config={"model": "anthropic/claude-3-haiku"},  # Better model
)

task = CostAwareTask(
    description="More detailed and specific instructions here...",
    expected_output="Very clear expected output format",
    agent=agent,
)
```

---

## API Reference

### CostAwareAgent

```python
CostAwareAgent(
    role: str,                  # Required: Agent's role
    goal: str,                  # Required: What agent should achieve
    backstory: str = None,      # Optional: Context/persona
    llm_config: dict = None,    # Optional: Model configuration
    tools: list = None,         # Optional: CrewAI tools
    verbose: bool = False       # Optional: Enable logging
)
```

### CostAwareTask

```python
CostAwareTask(
    description: str,           # Required: Task instructions
    expected_output: str,       # Required: Expected result format
    agent: CostAwareAgent,      # Required: Agent to execute task
    cost_limit: float = None,   # Optional: Budget for this task
    tools: list = None          # Optional: Tools available
)
```

### CostAwareCrew

```python
CostAwareCrew(
    tasks: List[CostAwareTask],        # Required: Tasks to execute
    agents: List[CostAwareAgent],      # Required: Available agents
    config: CrewConfig = None,         # Optional: Execution config
    cost_limit: float = None           # Optional: Total budget
)

# Methods
crew.kickoff() → dict                 # Execute crew, return result
crew.kickoff_for_each(inputs) → list  # Run crew multiple times
```

### CrewConfig

```python
CrewConfig(
    process: str = "sequential",       # Execution pattern
    max_iterations: int = 10,          # Max attempts per task
    verbosity: int = 0,                # Log level (0-2)
    llm_config: dict = None            # Default LLM settings
)
```

---

## Next Steps

1. ✅ **Install**: `pip install cost-orchestrator`
2. ✅ **Configure API Keys**: Set `OPENROUTER_API_KEY` env var
3. ✅ **Try Example**: Run `examples/crewai_example.py`
4. ✅ **Build Your Crew**: Create agents and tasks for your use case

---

## Support & Resources

- **GitHub Issues**: Report bugs or request features
- **CrewAI Docs**: https://docs.crewai.com/
- **Example Projects**: See `examples/` directory in MR-Krabs repo
- **Community**: Join our Discord for help and collaboration

---

*Built with ❤️ by the MR-Krabs team*
