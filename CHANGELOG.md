# Changelog

All notable changes to cost-orchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-05

### Added

#### Core Features
- **Zero-config `ask()` API** - Simple function call interface for cost-optimized LLM tasks
- **4-tier escalation system** (L0-L3) with automatic fallback on failure
- **Budget tracking & enforcement** with configurable daily limits ($10/day default)
- **Cost reporting** via CLI commands (`stats`, `daily-report`, `efficiency-report`, `trend-report`)
- **JSON/CSV export** for cost data analysis

#### Advanced Features
- **Budget-aware tier selection** (P4-2) - Automatic tier adjustment based on remaining budget
  - 5 budget tiers with intelligent fallback strategies
  - Override mechanism via `tier=` parameter
  - Emergency mode below 15% budget
  
- **Cost-aware error handling** (P4-3) - Different recovery strategies per error type
  - Network/Timeout: Retry with backoff (5-7 attempts)
  - Rate Limit: Retry with delay (3 attempts)
  - Context Too Long: Simplify & retry (3 attempts, 40-75% reduction)
  - Auth Error: Fail immediately (not retryable)
  - Budget Exceeded: Escalate error (stops all tasks)

- **Daily cost reports** (P4-4) - Comprehensive spending analysis
  - Tier breakdown with efficiency scores
  - Task totals and usage patterns
  - Warning alerts at 80% and emergency cap at 150%
  
- **Metrics collection** (P4-5) - Performance tracking
  - Tier efficiency rankings
  - Cost trends over time
  - Optimization suggestions

#### Integrations
- **CrewAI integration** with cost tracking
- **LangChain callback handler** for cost monitoring in chains
- **LM Studio support** for free local inference (treated as L0 tier)

#### CLI Commands
- `cost-orchestrator init` - Interactive setup wizard
- `cost-orchestrator doctor` - System diagnostics
- `cost-orchestrator run <task>` - Execute tasks with cost optimization
- `cost-orchestrator stats` - View cost summary
- `cost-orchestrator daily-report [days]` - Generate daily reports
- `cost-orchestrator efficiency-report` - Analyze tier efficiency
- `cost-orchestrator trend-report [days]` - Cost trend analysis

### Changed

- Package renamed to `cost-orchestrator` for PyPI distribution
- CLI entry point updated from `orchestrator` to `cost-orchestrator`

### Technical Details

#### Testing
- **742 tests** passing with comprehensive coverage
- **67% overall code coverage** (3,199/4,147 lines)
- Core modules: 75-100% coverage
  - `tier_manager.py`: 85%
  - `cost.py`: 75%
  - `error_classifier.py`: 81%
  - Infrastructure modules: 99%

#### Dependencies
- Python 3.11+ required
- Core dependencies: requests, pydantic, pyyaml, rich, click, structlog
- Optional dev dependencies: pytest, pytest-cov, mypy, black, ruff

### Example Usage

```python
from cost_orchestrator import ask

# Basic usage
result = ask("Write a Python function that sorts a list")
print(result.output)
print(f"Cost: ${result.cost:.4f}")  # Typically $0.001 for simple tasks
print(f"Tier used: {result.tier_used}")  # L0-Coder for most tasks

# With custom budget
result = ask("Build a REST API", budget=5.0)

# Force specific tier
result = ask("Debug complex issue", tier="L2")
```

### Known Limitations

- Initial release focuses on OpenRouter and LM Studio providers
- Additional providers (OpenAI, Anthropic direct) planned for future versions
- Web UI not yet available (CLI-only interface)

### Migration Guide

This is the initial release. No migration needed.

---

## Future Roadmap

### 0.2.0 (Planned)
- Direct OpenAI and Anthropic API support
- Improved context compression algorithms
- Multi-session cost aggregation
- Web dashboard for cost visualization

### 0.3.0 (Planned)
- Plugin system for custom tier definitions
- Advanced retry strategies with machine learning
- Team collaboration features (shared budgets, role-based access)
