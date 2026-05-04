# Story P2-6: Configuration Validation & Migration Tools

**Priority**: P2 (Medium - Improves Reliability)  
**Estimate**: 0.5 weeks  
**Phase**: Week 16a

---

## User Story

As a developer  
I want configuration validation and migration tools  
So that I can easily upgrade from v1 to v2 configuration and catch errors early

---

## Acceptance Criteria

### AC1: Config Validation

- [ ] Config validated on every `orchestrator` command
- [ ] Clear error messages for invalid config
- [ ] Warning messages for deprecated settings
- [ ] Config structure validation
- [ ] Provider key validation (format check)
- [ ] Budget value validation (numeric, positive)

### AC2: Validation Errors

- [ ] Missing required fields reported
- [ ] Invalid field types reported
- [ ] Invalid enum values reported
- [ ] Invalid URL formats reported
- [ ] Invalid pricing formats reported
- [ ] Errors actionable with fixes suggested

### AC3: Config Migration

- [ ] Migration tool for v1 → v2 configs
- [ ] Preserves user settings during migration
- [ ] Updates deprecated field names
- [ ] Adds new required fields with defaults
- [ ] Migration backup created automatically
- [ ] Migration roll-back possible

### AC4: Deprecated Settings

- [ ] List of deprecated settings documented
- [ ] Deprecation warnings on config load
- [ ] Migration path provided for each deprecated setting
- [ ] Warning messages appear in doctor output
- [ ] Scheduled removal timeline (3 releases)

### AC5: Init Wizard Updates

- [ ] `orchestrator init` creates v2 config
- [ ] Wizard validates config before saving
- [ ] Wizard explains new fields
- [ ] Wizard offers migration from existing config
- [ ] Wizard shows validation results

### AC6: Config Linting

- [ ] `orchestrator lint` command
- [ ] Reports all validation issues
- [ ] Suggests fixes for each issue
- [ ] Can auto-fix some issues
- [ ] Returns exit code on failure

---

## Technical Implementation

### Files to Create/Modify

1. `src/core/config_validator.py` - New validation module
2. `src/core/config_migrator.py` - New migration module
3. `src/cli/commands.py` - Add `lint` and migration commands
4. `src/core/config.py` - Integrate validation on load

### Implementation Plan

```python
# src/core/config_validator.py

from dataclasses import dataclass
from typing import Optional, List
from pydantic import BaseModel, Field, validator as pydantic_validator

@dataclass
class ValidationError:
    """Configuration validation error."""
    field: str
    message: str
    severity: str  # "error", "warning", "info"
    suggested_fix: Optional[str] = None

@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[ValidationError] = None
    warnings: List[ValidationError] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
    
    def add_error(self, field: str, message: str, fix: str | None = None):
        """Add an error."""
        self.errors.append(ValidationError(field, message, "error", fix))
        self.is_valid = False
    
    def add_warning(self, field: str, message: str, fix: str | None = None):
        """Add a warning."""
        self.warnings.append(ValidationError(field, message, "warning", fix))
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

class ConfigValidator:
    """Configuration validation for cost orchestrator."""
    
    DEPRECATED_SETTINGS = {
        "budget.daily_usd": {
            "replacement": "budget.daily_limit_usd",
            "message": "daily_usd is deprecated, use daily_limit_usd",
            "fix": "Rename to daily_limit_usd"
        },
        "providers.lmstudio.url": {
            "replacement": "providers.lmstudio.base_url",
            "message": "url is deprecated, use base_url",
            "fix": "Rename to base_url"
        },
    }
    
    REQUIRED_FIELDS = [
        "version",
        "budget.daily_limit_usd",
        "providers.openrouter.api_key_env",
    ]
    
    def validate(self, config: dict) -> ValidationResult:
        """Validate configuration."""
        result = ValidationResult(is_valid=True)
        
        # Check required fields
        self._check_required_fields(config, result)
        
        # Validate budget fields
        self._validate_budget(config, result)
        
        # Validate providers
        self._validate_providers(config, result)
        
        # Check for deprecated settings
        self._check_deprecated(config, result)
        
        # Validate provider keys
        self._validate_provider_keys(config, result)
        
        return result
    
    def _check_required_fields(self, config: dict, result: ValidationResult):
        """Check that required fields exist."""
        for field in self.REQUIRED_FIELDS:
            if not self._get_nested(config, field):
                result.add_error(
                    field,
                    f"Required field '{field}' is missing",
                    f"Add '{field}' to your configuration"
                )
    
    def _validate_budget(self, config: dict, result: ValidationResult):
        """Validate budget fields."""
        budget = config.get("budget", {})
        
        daily_limit = budget.get("daily_limit_usd")
        if daily_limit:
            try:
                value = float(daily_limit)
                if value <= 0:
                    result.add_error(
                        "budget.daily_limit_usd",
                        "Budget must be positive",
                        "Set to a positive number (e.g., 10.00)"
                    )
            except (ValueError, TypeError):
                result.add_error(
                    "budget.daily_limit_usd",
                    "Budget must be a valid number",
                    "Use format like '10.00' or 10.00"
                )
        
        emergency_cap = budget.get("emergency_cap_usd")
        if emergency_cap:
            try:
                value = float(emergency_cap)
                if value < 0:
                    result.add_error(
                        "budget.emergency_cap_usd",
                        "Emergency cap cannot be negative",
                        "Set to 0 or a positive number"
                    )
            except (ValueError, TypeError):
                result.add_error(
                    "budget.emergency_cap_usd",
                    "Emergency cap must be a valid number",
                    "Use format like '5.00' or 5.00"
                )
    
    def _validate_providers(self, config: dict, result: ValidationResult):
        """Validate provider configurations."""
        providers = config.get("providers", {})
        
        # Validate OpenRouter
        if "openrouter" in providers:
            openrouter = providers["openrouter"]
            if "api_key_env" not in openrouter:
                result.add_warning(
                    "providers.openrouter.api_key_env",
                    "OpenRouter provider has no api_key_env specified",
                    "Add api_key_env = 'OPENROUTER_API_KEY'"
                )
        
        # Validate LM Studio
        if "lmstudio" in providers:
            lmstudio = providers["lmstudio"]
            base_url = lmstudio.get("base_url")
            
            if base_url:
                if not base_url.startswith("http://") and not base_url.startswith("https://"):
                    result.add_error(
                        "providers.lmstudio.base_url",
                        "LM Studio URL must start with http:// or https://",
                        "Use format like 'http://localhost:1234/v1'"
                    )
                
                if not base_url.endswith("/v1"):
                    result.add_warning(
                        "providers.lmstudio.base_url",
                        "LM Studio URL should end with /v1",
                        "Use format like 'http://localhost:1234/v1'"
                    )
    
    def _check_deprecated(self, config: dict, result: ValidationResult):
        """Check for deprecated settings."""
        for deprecated, info in self.DEPRECATED_SETTINGS.items():
            if self._get_nested(config, deprecated):
                result.add_warning(
                    deprecated,
                    info["message"],
                    info["fix"]
                )
    
    def _validate_provider_keys(self, config: dict, result: ValidationResult):
        """Validate provider API key environment variables exist."""
        providers = config.get("providers", {})
        
        # Check if env vars exist (best effort - may not work in all contexts)
        for provider_name, provider_config in providers.items():
            if "api_key_env" in provider_config:
                import os
                env_var = provider_config["api_key_env"]
                if env_var not in os.environ:
                    result.add_warning(
                        f"providers.{provider_name}.api_key_env",
                        f"Environment variable '{env_var}' is not set",
                        f"Set {env_var} in your environment"
                    )
    
    def _get_nested(self, config: dict, field_path: str) -> any:
        """Get nested field from config."""
        keys = field_path.split(".")
        value = config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value
```

```python
# src/core/config_migrator.py

from copy import deepcopy
from datetime import datetime

class ConfigMigrator:
    """Migration tool for config v1 → v2."""
    
    FIELD_MAPPINGS = {
        "budget.daily_usd": "budget.daily_limit_usd",
        "providers.lmstudio.url": "providers.lmstudio.base_url",
        "providers.openrouter.url": "providers.openrouter.base_url",
    }
    
    DEPRECATED_REMOVALS = [
        "legacy.mode",
        "experimental.features",
    ]
    
    DEFAULT_VALUES = {
        "budget.task_limit_usd": "1.00",
        "budget.warning_threshold": "0.8",
        "budget.failure_mode": "fail_open_with_alert",
        "budget.emergency_cap_usd": "5.00",
        "version": "2.0",
    }
    
    def migrate(self, config: dict, backup: bool = True) -> dict:
        """Migrate config to v2."""
        # Create backup
        if backup:
            backup_path = self._create_backup(config)
        
        # Deep copy to avoid mutating original
        migrated = deepcopy(config)
        
        # Map deprecated fields
        migrated = self._map_fields(migrated)
        
        # Remove deprecated fields
        migrated = self._remove_deprecated(migrated)
        
        # Add default values for new required fields
        migrated = self._add_defaults(migrated)
        
        # Update version
        migrated["version"] = "2.0"
        
        return migrated
    
    def _map_fields(self, config: dict) -> dict:
        """Map deprecated field names to new names."""
        for old_field, new_field in self.FIELD_MAPPINGS.items():
            value = self._get_nested(config, old_field)
            if value is not None:
                # Remove old field
                self._remove_nested(config, old_field)
                
                # Add new field
                self._set_nested(config, new_field, value)
        
        return config
    
    def _remove_deprecated(self, config: dict) -> dict:
        """Remove deprecated fields."""
        for field in self.DEPRECATED_REMOVALS:
            self._remove_nested(config, field)
        
        return config
    
    def _add_defaults(self, config: dict) -> dict:
        """Add default values for new required fields."""
        for field, default in self.DEFAULT_VALUES.items():
            if not self._get_nested(config, field):
                self._set_nested(config, field, default)
        
        return config
    
    def _create_backup(self, config: dict, backup_dir: str = ".config_backups") -> str:
        """Create backup of config."""
        import os
        from pathlib import Path
        
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"config_backup_{timestamp}.json"
        
        import json
        backup_file.write_text(json.dumps(config, indent=2))
        
        return str(backup_file)
```

```python
# src/cli/commands.py

def cmd_lint(config_path: Path | None = None) -> int:
    """Validate configuration and report issues."""
    from src.core.config_validator import ConfigValidator
    
    try:
        from src.core.config import load_config
        config = load_config(config_path)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return 1
    
    validator = ConfigValidator()
    result = validator.validate(config)
    
    print("=" * 70)
    print("  Configuration Lint Report")
    print("=" * 70)
    print()
    
    if result.has_errors():
        print("❌ Errors Found:")
        print("-" * 70)
        for error in result.errors:
            print(f"  ✗ [{error.field}] {error.message}")
            if error.suggested_fix:
                print(f"    Fix: {error.suggested_fix}")
        print()
    
    if result.has_warnings():
        print("⚠️  Warnings:")
        print("-" * 70)
        for warning in result.warnings:
            print(f"  ! [{warning.field}] {warning.message}")
            if warning.suggested_fix:
                print(f"    Fix: {warning.suggested_fix}")
        print()
    
    if not result.has_errors() and not result.has_warnings():
        print("✅ Configuration is valid!")
        print()
    
    print("=" * 70)
    
    return 0 if not result.has_errors() else 1
```

---

## Testing Requirements

### Unit Tests (test_config_validator.py, test_config_migrator.py)

1. `test_validate_required_fields` - Required fields checked
2. `test_validate_budget_positive` - Positive budget enforced
3. `test_validate_provider_keys` - Provider keys validated
4. `test_check_deprecated_fields` - Deprecated fields detected
5. `test_migrate_field_mappings` - Field mappings work
6. `test_migrate_add_defaults` - Defaults added correctly
7. `test_migration_backup` - Backup created on migration

### Integration Tests

1. Load invalid config → error reported
2. Run `orchestrator lint` on valid config → success
3. Run `orchestrator lint` on invalid config → errors reported
4. Migrate v1 config to v2 → all fields mapped
5. Init wizard validates before saving

---

## Out of Scope

- Automatic config fixes (user must confirm)
- Config comparison between versions
- Config history/audit trail
- Multi-config management
- Config encryption

---

## Dependencies

- P1 complete (core config infrastructure)
- All P2-1 through P2-5 (for comprehensive validation)

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Validation Speed** | <50ms |
| **Migration Speed** | <100ms |
| **Error Accuracy** | 100% |
| **Backup Size** | <1MB |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Migration tested with real v1 configs
- [ ] Documentation updated
- [ ] Wizard integration complete
- [ ] Error messages clear and actionable

---

## Success Metrics

- **Adoption**: 100% of v1 configs migrated to v2
- **Error Prevention**: 95%+ of config errors caught by validator
- **User Satisfaction**: Clear, actionable error messages
- **Migration Success**: 100% successful migrations

---

*Draft: April 26, 2026*
