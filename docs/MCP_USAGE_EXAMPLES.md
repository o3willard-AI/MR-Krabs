# MR-Krabs MCP Server - Usage Examples

**Version**: 1.0.0  
**Date**: May 7, 2026  
**Status**: Production Ready

This document provides practical examples for using the MR-Krabs MCP server in real-world scenarios.

---

## Example 1: Basic Session with Cost Estimation

### Scenario
You want to execute a simple task and know the cost beforehand.

### Steps

```bash
# Step 1: Initialize session with $5 budget
SESSION=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '''{"budget_limit": 5.0, "enforcement_mode": "notify_then_fail"}''')

echo $SESSION | jq .

# Output:
# {
#   "success": true,
#   "session_id": "sess_abc123",
#   "status": "active"
# }

# Extract session ID for use in subsequent commands
SESSION_ID=$(echo $SESSION | jq -r '.session_id')
```

```bash
# Step 2: Estimate cost before execution
ESTIMATE=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_estimate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"model\": \"google/gemma-7b-it\", \"input_tokens\": 500}")

echo $ESTIMATE | jq .estimated_cost

# Output: 0.014
```

```bash
# Step 3: Execute single agent task
RESULT=$(curl -s -X POST http://localhost:8000/tools/mcp_mrkrabs_agent_execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"agent_config\": {
      \"name\": \"assistant\",
      \"role\": \"Helpful Assistant\",
      \"goal\": \"Provide helpful responses\"
    },
    \"task\": \"Explain what quantum entanglement is in simple terms\"
  }")

echo $RESULT | jq .result
```

```bash
# Step 4: Check remaining budget
STATUS=$(curl -s http://localhost:8000/tools/mcp_mrkrabs_session_status/$SESSION_ID)
echo $STATUS | jq '{remaining: .budget_remaining, spent: .budget_spent}'
```

---

## Example 2: Multi-Agent Crew for Research Task

### Scenario
You need to research a topic and write an article using multiple specialized agents.

### Complete Workflow

```bash
#!/bin/bash
# save as: example_research_crew.sh

set -e

# Configuration
SERVER_URL="http://localhost:8000"
BUDGET=10.0

echo "=== MR-Krabs Research Crew Example ==="

# Step 1: Create session
echo "Creating session with \$$BUDGET budget..."
SESSION_RESPONSE=$(curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_session_init" \
  -H "Content-Type: application/json" \
  -d "{\"budget_limit\": $BUDGET, \"enforcement_mode\": \"notify_then_fail\"}")

SESSION_ID=$(echo $SESSION_RESPONSE | jq -r '.session_id')
echo "Session ID: $SESSION_ID"

# Step 2: Create research crew with multiple agents
echo ""
echo "Creating multi-agent research crew..."
CREW_RESPONSE=$(curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_crew_create" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"crew_config\": {
      \"agents\": [
        {
          \"name\": \"researcher\",
          \"role\": \"Research Analyst\",
          \"goal\": \"Gather accurate information from reliable sources and synthesize findings\",
          \"backstory\": \"You are an expert researcher with access to multiple knowledge bases. You excel at finding credible sources and identifying key patterns."
        },
        {
          \"name\": \"analyst\",
          \"role\": \"Data Analyst\",
          \"goal\": \"Analyze research findings and identify important trends\",
          \"backstory\": \"You are skilled at extracting insights from complex information and presenting them clearly."
        },
        {
          \"name\": \"writer\",
          \"role\": \"Technical Writer\",
          \"goal\": \"Create well-structured, engaging content based on research\",
          \"backstory\": \"You are a professional technical writer who can explain complex topics in accessible language."
        }
      ],
      \"tasks\": [
        {
          \"description\": \"Research the history and current state of large language models from 2017 to present. Include key milestones, breakthroughs, and major model releases.",
          \"expected_output\": \"A comprehensive research summary with timeline of major developments\",
          \"agent_name\": \"researcher\"
        },
        {
          \"description\": \"Analyze the research findings to identify key trends in model architecture, training methods, and capabilities evolution.",
          \"expected_output\": \"Structured analysis highlighting important patterns and shifts in the field\",
          \"agent_name\": \"analyst\"
        },
        {
          \"description\": \"Write a 1500-word article titled 'The Evolution of Large Language Models' suitable for publication on a tech blog.",
          \"expected_output\": \"Complete article with introduction, body sections, and conclusion\",
          \"agent_name\": \"writer\"
        }
      ],
      \"verbose\": true
    }
  }")

CREW_ID=$(echo $CREW_RESPONSE | jq -r '.crew_id')
echo "Crew ID: $CREW_ID"
echo "Agents: $(echo $CREW_RESPONSE | jq -r '.agents_count')"
echo "Tasks: $(echo $CREW_RESPONSE | jq -r '.tasks_count')"

# Step 3: Execute the crew
echo ""
echo "Executing crew tasks..."
EXECUTION=$(curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_crew_execute" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"crew_id\": \"$CREW_ID\"}")

echo $EXECUTION | jq '.results'

# Step 4: Check costs
echo ""
echo "Cost breakdown:"
echo $EXECUTION | jq '.cost_breakdown'

# Step 5: Get analytics
echo ""
echo "Session analytics:"
ANALYTICS=$(curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_analytics_summary" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\"}")

echo $ANALYTICS | jq '.data'

# Step 6: Close session
echo ""
echo "Closing session..."
curl -s -X DELETE "$SERVER_URL/tools/mcp_mrkrabs_session_close/$SESSION_ID" | jq .

echo ""
echo "=== Complete ==="
```

### Run It

```bash
chmod +x example_research_crew.sh
./example_research_crew.sh
```

---

## Example 3: Budget-Aware Execution with Checks

### Scenario
You want to execute multiple tasks while staying within a strict budget.

### Python Script

```python
#!/usr/bin/env python3
"""
Budget-aware multi-task execution example
"""

import requests
import json
import time

SERVER_URL = "http://localhost:8000"

def create_session(budget_limit: float, enforcement_mode: str = "fail") -> str:
    """Create a new session and return session_id."""
    response = requests.post(
        f"{SERVER_URL}/tools/mcp_mrkrabs_session_init",
        json={
            "budget_limit": budget_limit,
            "enforcement_mode": enforcement_mode,
            "warning_threshold": 70.0
        }
    )
    result = response.json()
    if not result.get("success"):
        raise Exception(f"Failed to create session: {result}")
    return result["session_id"]

def estimate_cost(session_id: str, model: str, input_tokens: int) -> float:
    """Estimate cost for a task."""
    response = requests.post(
        f"{SERVER_URL}/tools/mcp_mrkrabs_cost_estimate",
        json={
            "session_id": session_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": 200  # Estimate output
        }
    )
    return response.json()["estimated_cost"]

def check_budget(session_id: str, would_spend: float) -> tuple[bool, dict]:
    """Check if we can afford a task."""
    response = requests.post(
        f"{SERVER_URL}/tools/mcp_mrkrabs_budget_check",
        json={
            "session_id": session_id,
            "would_spend": would_spend
        }
    )
    result = response.json()
    return result["can_proceed"], result

def execute_task(session_id: str, task: str) -> dict:
    """Execute a single agent task."""
    response = requests.post(
        f"{SERVER_URL}/tools/mcp_mrkrabs_agent_execute",
        json={
            "session_id": session_id,
            "agent_config": {
                "name": "assistant",
                "role": "Helpful Assistant",
                "goal": "Provide accurate and helpful responses"
            },
            "task": task,
            "model_override": "google/gemma-7b-it"  # Use cheap model
        }
    )
    return response.json()

def get_session_status(session_id: str) -> dict:
    """Get current session status."""
    response = requests.get(f"{SERVER_URL}/tools/mcp_mrkrabs_session_status/{session_id}")
    return response.json()

def close_session(session_id: str) -> dict:
    """Close the session."""
    response = requests.delete(f"{SERVER_URL}/tools/mcp_mrkrabs_session_close/{session_id}")
    return response.json()

def main():
    """Execute multiple tasks with budget awareness."""
    
    # Configuration
    BUDGET = 5.0
    TASKS = [
        "What is photosynthesis and how does it work?",
        "Explain the concept of blockchain in simple terms.",
        "Summarize the key points of Einstein's theory of relativity.",
        "What are neural networks and how do they learn?",
        "Describe the water cycle and its importance."
    ]
    
    print(f"=== Budget-Aware Task Execution ===")
    print(f"Budget: ${BUDGIT}")
    print(f"Tasks: {len(TASKS)}")
    print()
    
    # Create session
    print("Creating session...")
    session_id = create_session(BUDGET, enforcement_mode="fail")
    print(f"Session ID: {session_id}")
    print()
    
    completed_tasks = 0
    failed_tasks = 0
    
    for i, task in enumerate(TASKS, 1):
        print(f"[{i}/{len(TASKS)}] Task: {task[:50]}...")
        
        # Estimate cost
        estimated = estimate_cost(session_id, "google/gemma-7b-it", 300)
        print(f"  Estimated cost: \${estimated:.4f}")
        
        # Check budget
        can_proceed, budget_info = check_budget(session_id, estimated)
        remaining = budget_info.get("remaining_budget", 0)
        print(f"  Remaining budget: \${remaining:.2f}")
        
        if not can_proceed:
            print(f"  ❌ Budget exceeded, skipping task")
            failed_tasks += 1
            continue
        
        # Execute task
        try:
            result = execute_task(session_id, task)
            if result.get("success"):
                completed_tasks += 1
                actual_cost = result.get("cost", 0)
                print(f"  ✅ Completed (actual cost: \${actual_cost:.4f})")
            else:
                failed_tasks += 1
                print(f"  ❌ Failed: {result.get('error')}")
        except Exception as e:
            failed_tasks += 1
            print(f"  ❌ Error: {e}")
        
        print()
    
    # Final status
    status = get_session_status(session_id)
    print("=== Final Status ===")
    print(f"Tasks completed: {completed_tasks}/{len(TASKS)}")
    print(f"Tasks failed: {failed_tasks}")
    print(f"Total spent: \${status['budget_spent']:.2f}")
    print(f"Remaining: \${status['budget_remaining']:.2f}")
    print()
    
    # Close session
    close_result = close_session(session_id)
    print(f"Session closed: {close_result}")

if __name__ == "__main__":
    main()
```

### Run It

```bash
python3 budget_aware_execution.py
```

---

## Example 4: Analytics and Cost Optimization

### Scenario
Analyze your spending patterns and get optimization recommendations.

### cURL Commands

```bash
#!/bin/bash
# Save as: example_analytics.sh

SERVER_URL="http://localhost:8000"

echo "=== MR-Krabs Analytics Example ==="
echo ""

# Get summary for last 7 days
echo "1. Analytics Summary (7 days):"
curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_analytics_summary" \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq '.data'

echo ""
echo "2. Cost Trend Analysis:"
curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_cost_trend" \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq '.data'

echo ""
echo "3. Efficiency Report & Recommendations:"
curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_efficiency_report" \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq '.data.optimization_suggestions'

echo ""
echo "4. Export to CSV:"
curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_export_csv" \
  -H "Content-Type: application/json" \
  -d '{
    "period_days": 30,
    "output_dir": "/tmp",
    "output_file": "mrkrbs_costs.csv"
  }' | jq .

echo ""
echo "5. Export to JSON:"
curl -s -X POST "$SERVER_URL/tools/mcp_mrkrabs_export_json" \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq '.data.metadata'

echo ""
echo "=== Complete ==="
```

### Run It

```bash
chmod +x example_analytics.sh
./example_analytics.sh
```

---

## Example 5: Using with MCP Client Libraries

### Scenario
Integrate MR-Krabs tools into your application code.

### Python (using requests)

```python
#!/usr/bin/env python3
"""
MCP Server client wrapper class
"""

from typing import Optional, Dict, Any
import requests

class MRKrabsClient:
    """Client for MR-Krabs MCP Server."""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
    
    # Session Management
    def init_session(self, budget_limit: float = 10.0, **kwargs) -> str:
        """Initialize a new session."""
        payload = {"budget_limit": budget_limit, **kwargs}
        response = self.session.post(f"{self.base_url}/tools/mcp_mrkrabs_session_init", json=payload)
        result = response.json()
        if not result.get("success"):
            raise Exception(f"Session init failed: {result}")
        return result["session_id"]
    
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get session status."""
        response = self.session.get(f"{self.base_url}/tools/mcp_mrkrabs_session_status/{session_id}")
        return response.json()
    
    def close_session(self, session_id: str) -> Dict[str, Any]:
        """Close a session."""
        response = self.session.delete(f"{self.base_url}/tools/mcp_mrkrabs_session_close/{session_id}")
        return response.json()
    
    # Cost Management
    def estimate_cost(self, session_id: str, model: str, input_tokens: int = None, prompt_text: str = None) -> float:
        """Estimate cost for an LLM call."""
        payload = {"session_id": session_id, "model": model}
        if input_tokens:
            payload["input_tokens"] = input_tokens
        if prompt_text:
            payload["prompt_text"] = prompt_text
        
        response = self.session.post(f"{self.base_url}/tools/mcp_mrkrabs_cost_estimate", json=payload)
        return response.json()["estimated_cost"]
    
    def check_budget(self, session_id: str, would_spend: float) -> bool:
        """Check if expenditure fits budget."""
        response = self.session.post(
            f"{self.base_url}/tools/mcp_mrkrabs_budget_check",
            json={"session_id": session_id, "would_spend": would_spend}
        )
        return response.json()["can_proceed"]
    
    # CrewAI Tools
    def create_crew(self, session_id: str, agents: list, tasks: list) -> str:
        """Create a multi-agent crew."""
        payload = {
            "session_id": session_id,
            "crew_config": {"agents": agents, "tasks": tasks}
        }
        response = self.session.post(f"{self.base_url}/tools/mcp_mrkrabs_crew_create", json=payload)
        result = response.json()
        if not result.get("success"):
            raise Exception(f"Crew creation failed: {result}")
        return result["crew_id"]
    
    def execute_crew(self, session_id: str, crew_id: str) -> Dict[str, Any]:
        """Execute a crew."""
        response = self.session.post(
            f"{self.base_url}/tools/mcp_mrkrabs_crew_execute",
            json={"session_id": session_id, "crew_id": crew_id}
        )
        return response.json()
    
    def execute_agent(self, session_id: str, task: str, agent_name: str = "assistant") -> Dict[str, Any]:
        """Execute a single agent task."""
        payload = {
            "session_id": session_id,
            "agent_config": {
                "name": agent_name,
                "role": "Assistant",
                "goal": "Help with tasks"
            },
            "task": task
        }
        response = self.session.post(f"{self.base_url}/tools/mcp_mrkrabs_agent_execute", json=payload)
        return response.json()

# Usage Example
if __name__ == "__main__":
    # Initialize client
    client = MRKrabsClient()
    
    # Create session
    session_id = client.init_session(budget_limit=10.0)
    print(f"Session created: {session_id}")
    
    # Estimate cost
    cost = client.estimate_cost(session_id, "google/gemma-7b-it", input_tokens=500)
    print(f"Estimated cost: \${cost:.4f}")
    
    # Execute task
    result = client.execute_agent(session_id, "What is machine learning?")
    print(f"Result: {result['result'][:100]}...")
    
    # Close session
    final_status = client.close_session(session_id)
    print(f"Total spent: \${final_status['final_spending']:.2f}")
```

---

## Example 6: Docker Deployment (Future)

### Scenario
Deploy MR-Krabs MCP Server in production using Docker.

**Note**: This is planned for Phase 5-S1. Here's a preview of what it will look like.

### docker-compose.yml

```yaml
version: '3.8'

services:
  mrkrabs-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8000
      - SESSION_TTL=3600
      - VAULT_MASTER_KEY_FILE=/app/vault/master.key
    volumes:
      - vault_data:/app/vault
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  vault_data:
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create vault directory
RUN mkdir -p /app/vault

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3   CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["python", "-m", "src.mcp.server"]
```

### Deploy

```bash
docker-compose up -d

# Check logs
docker-compose logs -f mrkrabs-mcp

# Access API
curl http://localhost:8000/health
```

---

## Summary

These examples demonstrate:

1. **Basic session management** with cost estimation
2. **Multi-agent crews** for complex tasks
3. **Budget-aware execution** patterns
4. **Analytics and optimization** workflows
5. **Client library** integration
6. **Docker deployment** (preview)

For more detailed API documentation, see:
- `MCP_USER_GUIDE.md` - Complete user guide
- `MCP_TOOLS_REFERENCE.md` - Tool schema reference
- `TROUBLESHOOTING.md` - Common issues and solutions

---

**Last Updated**: May 7, 2026  
**Version**: 1.0.0
