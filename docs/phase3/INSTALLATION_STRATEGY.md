# Phase 3 Installation & Distribution Strategy

**Date**: May 5, 2026  
**Status**: Planning  
**Priority**: P0 - Critical for user experience

---

## Current MR-Krabs Distribution Model

### How It Works Now:

```bash
# User installs from PyPI
pip install cost-orchestrator

# That's it! Dependencies auto-resolved:
# - requests>=2.31.0        (HTTP calls)
# - pydantic>=2.5.0         (Validation)
# - pyyaml>=6.0.1           (Config parsing)
# - rich>=13.7.0            (CLI formatting)
# - click>=8.1.7            (CLI framework)
# - structlog>=23.2.0       (Logging)
```

**Key Characteristics:**
- ✅ Single `pip install` command
- ✅ All dependencies auto-resolved by pip
- ✅ Minimal friction for users
- ✅ Works with virtual environments naturally
- ✅ Version pins in `pyproject.toml` ensure stability

---

## CrewAI Integration Options Analysis

### Option 1: Hard Dependency (Required) ❌ NOT RECOMMENDED

```python
# pyproject.toml
dependencies = [
    "requests>=2.31.0",
    # ... existing deps ...
    "crewai>=0.70.0",  # ← REQUIRED for ALL users
]
```

**Pros:**
- Simple - CrewAI always available
- No optional imports needed
- Works out of the box

**Cons:**
- ❌ **Breaks backward compatibility** - Users who just want `ask()` get CrewAI whether they want it or not
- ❌ **Increases install size** significantly (~50MB+ for CrewAI + dependencies)
- ❌ **Slower installation** - More packages to download
- ❌ **More potential conflicts** - CrewAI has its own dependency tree
- ❌ **Forces upgrade path** - Users can't stay on simple API

**Impact Analysis:**
```
Current install size: ~15MB
With CrewAI required: ~65MB  (+40MB, +267% increase)

Current install time: ~5 seconds  
With CrewAI required: ~20-30 seconds (+25 seconds)
```

**Verdict**: **REJECTED** - Violates "zero-config" philosophy and breaks existing users.

---

### Option 2: Optional Dependency (Extras) ✅ RECOMMENDED

```python
# pyproject.toml
dependencies = [
    "requests>=2.31.0",
    # ... existing deps ...
    # NO CrewAI here!
]

[project.optional-dependencies]
crewai = [
    "crewai>=0.70.0",      # Core CrewAI framework
    "crewai-tools>=0.12.0", # Optional tools (if needed)
]

dev = [
    "pytest>=7.4.0",
    # ... dev deps ...
    "crewai>=0.70.0",  # Dev installs include CrewAI for testing
]
```

**Installation Patterns:**

**Pattern A: Basic Installation (No CrewAI)**
```bash
pip install cost-orchestrator
# Users get existing functionality only
# ask() API works, no multi-agent features
```

**Pattern B: With CrewAI Support**
```bash
pip install cost-orchestrator[crewai]
# Users get both basic + CrewAI features
# Can use ask() AND multi-agent crews
```

**Pattern C: Development Installation**
```bash
pip install -e ".[dev,crewai]"
# Developers get everything for testing
```

**Pros:**
- ✅ **Maintains backward compatibility** - Existing installs unchanged
- ✅ **User choice** - Install only what you need
- ✅ **Smaller base install** - Core package stays lean
- ✅ **Clean upgrade path** - Users opt-in to CrewAI features
- ✅ **Follows Python best practices** - Standard `pip install pkg[extra]` pattern

**Cons:**
- ⚠️ Slightly more complex import handling (needs try/except)
- ⚠️ Documentation must explain both installation paths
- ⚠️ CLI needs to detect and handle missing CrewAI gracefully

**Verdict**: **RECOMMENDED** - Best balance of flexibility and simplicity.

---

### Option 3: Lazy Loading with Auto-Prompt ⚠️ CONSIDER FOR FUTURE

```python
# When user tries to use CrewAI features...
try:
    from crewai import Agent, Task, Crew
except ImportError:
    print("💡 To use CrewAI features, install with:")
    print("   pip install cost-orchestrator[crewai]")
    raise
```

**Pros:**
- Most user-friendly error messages
- Auto-detects missing dependency at runtime

**Cons:**
- Can be confusing if user doesn't understand the error
- Requires careful error handling throughout codebase

**Verdict**: **IMPLEMENT alongside Option 2** - Best of both worlds.

---

## Recommended Implementation: Optional Dependencies with Smart Detection

### 1. Update `pyproject.toml`

```toml
[project]
name = "cost-orchestrator"
version = "0.1.0-dev"
dependencies = [
    "requests>=2.31.0",
    "pydantic>=2.5.0",
    "pyyaml>=6.0.1",
    "rich>=13.7.0",
    "click>=8.1.7",
    "structlog>=23.2.0",
    # CrewAI NOT in core dependencies!
]

[project.optional-dependencies]
# CrewAI multi-agent framework (optional)
crewai = [
    "crewai>=0.70.0,<1.0.0",      # Pin major version for stability
    "langchain-community>=0.2.0",  # CrewAI dependency (explicit)
]

# Development dependencies
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "mypy>=1.7.0",
    "black>=23.11.0",
    "ruff>=0.1.6",
    "pre-commit>=3.6.0",
    # Include CrewAI for testing multi-agent features
    "crewai>=0.70.0,<1.0.0",
]

# All dependencies (for Docker/images)
all = [
    "cost-orchestrator[crewai,dev]",
]
```

**Rationale:**
- `crewai` as optional extra → Users choose when to install
- Version pinning (`>=0.70.0,<1.0.0`) → Prevent breaking changes
- Include in `dev` → Developers always have it for testing
- Separate from core → Base package stays minimal

---

### 2. Import Strategy with Fallback

Create a compatibility utility module:

```python
# src/utils/crewai_compat.py

from typing import TYPE_CHECKING, Optional
import importlib

# Type checking only (doesn't require CrewAI installed)
if TYPE_CHECKING:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool

# Runtime check
_crewai_available: Optional[bool] = None

def is_crewai_available() -> bool:
    """Check if CrewAI is installed and importable."""
    global _crewai_available
    
    if _crewai_available is None:
        try:
            import crewai
            from crewai import Agent, Task, Crew
            _crewai_available = True
        except ImportError:
            _crewai_available = False
    
    return _crewai_available

def require_crewai(feature_name: str = "this feature") -> None:
    """Raise helpful error if CrewAI not installed.
    
    Args:
        feature_name: Name of the feature for error message
        
    Raises:
        ImportError: With installation instructions
    """
    if not is_crewai_available():
        raise ImportError(
            f"CrewAI is required for {feature_name}. "
            f"Install with:\n\n"
            f"   pip install cost-orchestrator[crewai]\n\n"
            f"This adds the CrewAI multi-agent framework (~50MB)."
            f"Your existing code will continue to work without it."
        )

# Lazy imports for type hints
def get_crewai_classes():
    """Get CrewAI classes, raising helpful error if not available."""
    require_crewai("CrewAI classes")
    
    from crewai import Agent, Task, Crew, Process
    return Agent, Task, Crew, Process
```

**Usage in Code:**

```python
# src/agents/cost_aware_agent.py

from src.utils.crewai_compat import is_crewai_available, require_crewai

class CostAwareAgent:
    """Enhanced agent with cost tracking."""
    
    def __init__(self, role: str, goal: str, **kwargs):
        # Check CrewAI availability early
        require_crewai("CostAwareAgent")
        
        # Now safe to import
        from crewai import Agent as BaseAgent
        
        self.base_agent = BaseAgent(...)
```

---

### 3. Backward-Compatible `ask()` API

The existing `ask()` function must work without CrewAI:

```python
# src/__init__.py

from src.utils.crewai_compat import is_crewai_available

def ask(
    prompt: str,
    system_prompt: str = None,
    tier: str = None,
    auto_escalate: bool = True,
) -> AskResult:
    """Execute a prompt with cost optimization.
    
    This API works WITHOUT CrewAI installed for simple tasks.
    For multi-agent workflows, install CrewAI and use CostAwareCrew.
    """
    
    if is_crewai_available():
        # Use CrewAI-backed implementation (better features)
        return _ask_with_crewai(prompt, system_prompt, tier, auto_escalate)
    else:
        # Fall back to original single-agent implementation
        return _ask_legacy(prompt, system_prompt, tier, auto_escalate)

def _ask_with_crewai(...) -> AskResult:
    """New CrewAI-backed ask() for enhanced features."""
    from src.agents import CostAwareAgent, CostAwareTask, CostAwareCrew
    
    # Create single-agent crew
    agent = CostAwareAgent(role='coder', ...)
    task = CostAwareTask(description=prompt, agent=agent)
    crew = CostAwareCrew(agents=[agent], tasks=[task])
    
    result = crew.kickoff()
    return _convert_crew_output_to_ask_result(result)

def _ask_legacy(...) -> AskResult:
    """Original ask() implementation (no CrewAI)."""
    orchestrator = LLMOrchestrator()
    
    result = orchestrator.call_llm_with_retry(
        tier=tier or _get_default_tier(),
        system_prompt=system_prompt or "You are helpful",
        user_prompt=prompt,
    )
    
    return AskResult(
        output=result['output'],
        cost=result['cost'],
        # ... etc
    )
```

**Benefits:**
- Existing users: Zero changes needed, same behavior
- New users with CrewAI: Get enhanced features automatically
- Clear upgrade path: Install CrewAI when ready for multi-agent

---

### 4. CLI Integration with Graceful Degradation

```python
# src/cli/main.py

import click
from src.utils.crewai_compat import is_crewai_available

@click.group()
def main():
    """Cost-Optimized AI Orchestrator"""
    pass

@main.command()
def ask():
    """Ask a question (works without CrewAI)."""
    # Basic functionality always available
    pass

@main.group()
def crews():
    """Manage CrewAI workflows (requires CrewAI)."""
    if not is_crewai_available():
        click.secho(
            "⚠️  CrewAI is not installed. Install with:\n\n"
            "   pip install cost-orchestrator[crewai]\n",
            fg='yellow'
        )
        raise SystemExit(1)

@crews.command()
def list():
    """List available crew templates."""
    # Only works if CrewAI installed (checked by @crews group)
    from src.agents.templates import get_available_templates
    
    for template in get_available_templates():
        click.echo(f"  {template.name} - {template.description}")
```

---

### 5. Documentation Strategy

Update README.md with clear installation paths:

```markdown
## Installation

### Basic Installation (Simple Tasks)

For simple question-answering and basic code generation:

```bash
pip install cost-orchestrator
```

This gives you the `ask()` API - everything works, no complexity.

### With Multi-Agent Support (Recommended for Complex Workflows)

For collaborative multi-agent workflows using CrewAI:

```bash
pip install cost-orchestrator[crewai]
```

This adds ~50MB but enables:
- Multiple specialized agents working together
- Pre-built crew templates (code review, debugging, etc.)
- Hierarchical task decomposition
- Real-time cost tracking per agent

### Development Installation

For contributors who want to test everything:

```bash
pip install -e ".[dev,crewai]"
```

---

## Usage Examples

### Simple Ask (No CrewAI Required)

```python
from cost_orchestrator import ask

result = ask("Write a sorting function")
print(result.output)  # Works with basic installation!
```

### Multi-Agent Crew (Requires CrewAI)

```python
# Install first: pip install cost-orchestrator[crewai]

from cost_orchestrator.agents import CostAwareCrew, create_code_review_crew

crew = create_code_review_crew(code_snippet="def buggy(): ...")
result = crew.kickoff()
print(result.raw)  # Professional code review from 3 specialized agents!
```
```

---

## Installation Flow Diagram

```
User decides what they need:
│
├─ Simple tasks only (ask() API)
│  │
│  └─ pip install cost-orchestrator
│     ├─ Install size: ~15MB
│     ├─ Install time: ~5s
│     └─ Features: ask(), cost tracking, CLI basics
│
├─ Multi-agent workflows (CrewAI features)
│  │
│  └─ pip install cost-orchestrator[crewai]
│     ├─ Install size: ~65MB (+50MB)
│     ├─ Install time: ~25s (+20s)
│     └─ Features: Everything above + crews, templates, collaboration
│
└─ Development/Testing
   │
   └─ pip install -e ".[dev,crewai]"
      ├─ Full source access
      ├─ Test frameworks included
      └─ All features enabled
```

---

## Migration Path for Existing Users

### Current Users (No CrewAI)

**Current state:**
```bash
$ pip list | grep cost
cost-orchestrator    0.1.0
```

**After Phase 3 release:**
```bash
# Nothing changes! Existing installation still works.
$ python -c "from cost_orchestrator import ask; print('✓ Works!')"
✓ Works!
```

**To upgrade to CrewAI features (optional):**
```bash
$ pip install --upgrade cost-orchestrator[crewai]
Collecting cost-orchestrator[crewai]
  Downloading crewai-0.70.0...
  Installing...
Successfully installed crewai-0.70.0 ...

# Now CrewAI features available!
$ python -c "from cost_orchestrator.agents import CostAwareCrew; print('✓ CrewAI ready!')"
✓ CrewAI ready!
```

---

## Testing Strategy

### Test Without CrewAI

```bash
# Test basic functionality (no CrewAI)
pytest tests/unit/test_basic_api.py -v
```

### Test With CrewAI

```bash
# Install CrewAI for testing
pip install -e ".[crewai]"

# Run full test suite
pytest tests/ -v --cov=src
```

### CI/CD Configuration

```yaml
# .github/workflows/test.yml

name: Tests

on: [push, pull_request]

jobs:
  test-basic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install base package (NO CrewAI)
        run: pip install -e .
      
      - name: Run basic tests
        run: pytest tests/unit/test_basic_api.py tests/unit/test_cost_tracking.py

  test-with-crewai:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install with CrewAI
        run: pip install -e ".[crewai]"
      
      - name: Run full test suite
        run: pytest tests/ -v --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Docker Image Strategy (Future)

If you create Docker images later:

```dockerfile
# Multi-stage build for efficiency

# Stage 1: Base image (no CrewAI)
FROM python:3.11-slim AS base
WORKDIR /app
COPY . .
RUN pip install cost-orchestrator
# Size: ~500MB

# Stage 2: Full image with CrewAI
FROM base AS full
RUN pip install cost-orchestrator[crewai]
# Size: ~600MB (+100MB for CrewAI)

# Usage:
# docker pull cost-orchestrator:latest      # Base (no CrewAI)
# docker pull cost-orchestrator:full        # With CrewAI
```

---

## Decision Summary

### ✅ RECOMMENDED APPROACH: Optional Dependencies with Smart Fallback

| Aspect | Decision |
|--------|----------|
| **Dependency Type** | Optional (`crewai` extra) |
| **Base Package** | No CrewAI (stays lean) |
| **Import Strategy** | Try/except with helpful errors |
| **API Compatibility** | `ask()` works without CrewAI |
| **Upgrade Path** | `pip install pkg[crewai]` |
| **Documentation** | Clear paths for both options |
| **Testing** | Separate test suites (with/without CrewAI) |

### Key Benefits:

1. **Zero Breaking Changes** - Existing users unaffected
2. **User Choice** - Install only what you need  
3. **Small Base Package** - Core functionality stays fast and lean
4. **Clear Upgrade Path** - Simple command to add CrewAI
5. **Follows Python Standards** - Uses standard `pip install pkg[extra]` pattern

### Trade-offs Accepted:

1. Slightly more complex import handling (managed by compat module)
2. Need dual code paths for some features (ask() with/without CrewAI)
3. Documentation must cover both installation options

---

## Implementation Checklist

- [ ] Update `pyproject.toml` with optional dependencies
- [ ] Create `src/utils/crewai_compat.py` compatibility layer
- [ ] Update `src/__init__.py` to support dual code paths
- [ ] Add graceful degradation to CLI commands
- [ ] Update README.md with installation options
- [ ] Create migration guide for existing users
- [ ] Update CI/CD to test both with and without CrewAI
- [ ] Write helper script for checking installation status
- [ ] Add install verification command: `cost-orchestrator --version --check-dependencies`

---

## Next Steps

1. **Review this document** - Does the optional dependency approach align with your goals?
2. **Decide on version pinning** - Should we pin CrewAI to `<1.0.0` or allow any `>=0.70.0`?
3. **Confirm documentation strategy** - Are the installation paths clear enough for users?
4. **Approve implementation checklist** - Any items missing or needing adjustment?

Once approved, we can proceed with updating `pyproject.toml` and implementing the compatibility layer!
