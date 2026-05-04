# Story P1-8: TOML Configuration File

**Priority**: P1 (High)  
**Estimate**: 2 days  
**Phase**: Week 2-3

---

## User Story

As a developer  
I want to configure the orchestrator via a simple TOML file  
So that I can customize settings without code changes and share configs across projects

---

## Acceptance Criteria

### AC1: Config File Location
- [ ] Default location: `~/.cost_orchestrator.toml` (user config)
- [ ] Project-specific: `.cost_orchestrator.toml` in project root (overrides user config)
- [ ] Project config takes precedence over user config

### AC2: Config Schema
- [ ] Supports these sections:
  ```toml
  version = "1.0"
  
  [budget]
  daily_usd = 10.0
  task_limit_usd = 1.0
  warning_threshold = 0.8
  emergency_cap_usd = 5.0
  failure_mode = "fail_open_with_alert"
  
  [providers.openrouter]
  api_key_env = "OPENROUTER_API_KEY"
  
  [providers.lmstudio]
  base_url = "http://127.0.0.1:1234/v1"
  ```

### AC3: Loading Behavior
- [ ] Loads user config from `~/.cost_orchestrator.toml`
- [ ] If project config exists, merges (project overrides user)
- [ ] Missing configs use sensible defaults
- [ ] Invalid TOML syntax shows helpful error

### AC4: Validation
- [ ] Validates budget values are positive numbers
- [ ] Validates provider configurations exist
- [ ] Invalid config shows which field is wrong
- [ ] Suggests running `orchestrator init` to fix

### AC5: Defaults
- [ ] If no config file: uses all defaults
- [ ] Daily budget: $10.00
- [ ] Task limit: $1.00
- [ ] Warning threshold: 80%
- [ ] Emergency cap: $5.00
- [ ] All providers use defaults from code

---

## Technical Implementation

### Files to Create/Modify
1. `src/core/config.py` - Config loading and validation
2. `src/cli/commands.py` - `cmd_init` writes config file

### Implementation Details

```python
# src/core/config.py

import tomli
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal

@dataclass
class BudgetConfig:
    daily_usd: Decimal = Decimal("10.00")
    task_limit_usd: Decimal = Decimal("1.00")
    warning_threshold: float = 0.8
    emergency_cap_usd: Decimal = Decimal("5.00")
    failure_mode: str = "fail_open_with_alert"

@dataclass
class ProviderConfig:
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None

@dataclass
class OrchestratorConfig:
    version: str = "1.0"
    budget: BudgetConfig = None
    providers: dict = None
    
    def __post_init__(self):
        if self.budget is None:
            self.budget = BudgetConfig()
        if self.providers is None:
            self.providers = {}

class ConfigManager:
    """Manages configuration loading and merging."""
    
    USER_CONFIG = Path.home() / ".cost_orchestrator.toml"
    PROJECT_CONFIG = Path.cwd() / ".cost_orchestrator.toml"
    
    @classmethod
    def load(cls, project_root: str = None) -> OrchestratorConfig:
        """Load configuration from user and project files."""
        config = cls._load_defaults()
        
        # Load user config
        if cls.USER_CONFIG.exists():
            user_config = cls._parse_config(cls.USER_CONFIG)
            config = cls._merge_config(config, user_config)
        
        # Load project config (overrides user)
        if project_root:
            project_path = Path(project_root) / ".cost_orchestrator.toml"
            if project_path.exists():
                project_config = cls._parse_config(project_path)
                config = cls._merge_config(config, project_config)
        elif cls.PROJECT_CONFIG.exists():
            project_config = cls._parse_config(cls.PROJECT_CONFIG)
            config = cls._merge_config(config, project_config)
        
        return config
    
    @classmethod
    def _load_defaults(cls) -> OrchestratorConfig:
        """Load default configuration."""
        return OrchestratorConfig(
            budget=BudgetConfig(),
            providers={
                "openrouter": ProviderConfig(api_key_env="OPENROUTER_API_KEY"),
                "lmstudio": ProviderConfig(),
            }
        )
    
    @classmethod
    def _parse_config(cls, path: Path) -> OrchestratorConfig:
        """Parse TOML config file."""
        try:
            with open(path, "rb") as f:
                data = tomli.load(f)
        except tomli.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML syntax in {path}: {e}")
        
        # Validate required fields
        if "budget" in data:
            cls._validate_budget(data["budget"])
        
        return cls._data_to_config(data)
    
    @classmethod
    def _validate_budget(cls, data: dict):
        """Validate budget configuration."""
        if "daily_usd" in data:
            if not isinstance(data["daily_usd"], (int, float)) or data["daily_usd"] <= 0:
                raise ValueError("budget.daily_usd must be positive")
        # ... more validations
    
    @classmethod
    def _merge_config(cls, base: OrchestratorConfig, override: OrchestratorConfig) -> OrchestratorConfig:
        """Merge override config into base config."""
        # Deep merge logic
        ...
    
    @classmethod
    def _data_to_config(cls, data: dict) -> OrchestratorConfig:
        """Convert dict to OrchestratorConfig."""
        ...
```

---

## Testing Requirements

### Unit Tests (test_config.py)
1. `test_load_user_config` - Loads from ~/.cost_orchestrator.toml
2. `test_load_project_config` - Loads from project root
3. `test_project_overrides_user` - Project config takes precedence
4. `test_invalid_toml_error` - Shows helpful error
5. `test_missing_config_uses_defaults` - All defaults applied
6. `test_budget_validation` - Rejects invalid budget values

### Integration Tests
1. Full workflow: init → config written → loaded correctly
2. Project with custom config → overrides work

---

## Out of Scope
- Environment variable overrides
- Config encryption
- Multi-profile configs (Phase 3)

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests pass
- [ ] Config loading tested with real files
- [ ] Error messages clear and actionable
