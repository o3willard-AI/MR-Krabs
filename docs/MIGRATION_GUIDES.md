# Migration Guides

## CrewAI Integration

### Before
```python
from crewai import Agent, Task, Crew

agent = Agent(role="coder", goal="Write code", backstory="Expert developer")
task = Task(description="Write auth middleware", agent=agent)
crew = Crew(agents=[agent], tasks=[task])
result = crew.kickoff()
```

### After
```python
from crewai import Agent, Task, Crew
from cost_orchestrator import ask

agent = Agent(role="coder", goal="Write code", backstory="Expert developer")
task = Task(description="Write auth middleware", agent=agent)
crew = Crew(agents=[agent], tasks=[task])
result = crew.kickoff()

# Track cost after execution
cost_result = ask("Write auth middleware")
print(f"Cost: ${cost_result.cost:.4f}, Tier: {cost_result.tier}")
```

**Diff**: Add 2 lines for cost tracking.

---

## LangChain Integration

### Before
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(model="gpt-4o")
result = llm.invoke([HumanMessage(content="Write auth middleware")])
```

### After
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from cost_orchestrator import ask

llm = ChatOpenAI(model="gpt-4o")
result = llm.invoke([HumanMessage(content="Write auth middleware")])

# Track cost with orchestrator
cost_result = ask("Write auth middleware")
print(f"Cost: ${cost_result.cost:.4f}")
```

**Diff**: Add 2 lines for cost tracking.

---

## Standalone Python

### Before
```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write auth middleware"}]
)
```

### After
```python
from cost_orchestrator import ask

result = ask("Write auth middleware")
print(result.output)
print(f"Cost: ${result.cost:.4f}")
```

**Diff**: Replace 5 lines with 3 lines. Automatic cost optimization.
