# MR-Krabs Testing Guide

## Quick Start

### Run All Tests
```bash
cd /home/sblanken/working/code/MR-Krabs
.venv/bin/python -m pytest tests/ -v
```

### Run Tests with Coverage
```bash
.venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Run Specific Test File
```bash
.venv/bin/python -m pytest tests/unit/test_commands.py -v
```

### Run Tests by Keyword
```bash
# Run tests matching "test_init"
.venv/bin/python -m pytest tests/ -k "test_init" -v

# Run tests in specific class
.venv/bin/python -m pytest tests/unit/test_commands.py::TestCmdInit -v
```

---

## Test Organization

### Test Directories

```
tests/
├── benchmarks/          # Performance benchmarks
├── e2e/                 # End-to-end integration tests
├── integrations/        # Third-party integration tests
└── unit/                # Unit tests for individual modules
```

### Test Naming Conventions

- **Unit tests**: `test_<module>_<function>.py`
- **Classes**: `Test<Module>`, `Test<Feature>`
- **Methods**: `test_<scenario>_<expected_result>`

**Example:**
```python
class TestCmdInit:
    def test_init_with_env_key(self):
        """Test initialization using environment API key."""
        ...
    
    def test_init_custom_config_path(self):
        """Test initialization with custom config file path."""
        ...
```

---

## Test Execution

### Basic Commands

| Command | Description |
|---------|-------------|
| `pytest tests/` | Run all tests |
| `pytest tests/unit/` | Run unit tests only |
| `pytest tests/e2e/` | Run E2E tests only |
| `pytest -v` | Verbose output |
| `pytest -x` | Stop on first failure |
| `pytest --tb=short` | Short traceback |

### Coverage Commands

| Command | Description |
|---------|-------------|
| `pytest --cov=src` | Show coverage summary |
| `pytest --cov=src --cov-report=html` | Generate HTML report |
| `pytest --cov=src --cov-report=term-missing` | Show missing lines |
| `pytest --cov=src --cov-report=xml` | Generate XML report (for CI) |

### Advanced Commands

| Command | Description |
|---------|-------------|
| `pytest --cov=src --cov-fail-under=80` | Fail if coverage < 80% |
| `pytest -q` | Quiet mode |
| `pytest --collect-only` | List tests without running |
| `pytest --cache-clear` | Clear pytest cache |

---

## Writing Tests

### Structure

```python
#!/usr/bin/env python3
"""Unit tests for <module>.py"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.<module> import <function, class>


class Test<ClassName>:
    """Tests for <ClassName> class."""
    
    def test_<scenario>_<expected_result>(self):
        """Brief description of what is being tested."""
        # Arrange
        setup = ...
        
        # Act
        result = ...
        
        # Assert
        assert result == expected
```

### Mocking Best Practices

#### Mock External APIs
```python
@patch('requests.get')
def test_fetch_models(self, mock_get):
    """Test model fetching with mocked API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "test"}]}
    mock_get.return_value = mock_response
    
    result = fetch_models()
    
    assert result == ["test"]
```

#### Mock Configuration
```python
@patch('src.cli.commands.load_config')
def test_dry_run_with_mock_config(self, mock_load):
    """Test dry run with mocked config."""
    mock_load.return_value = {
        "budget": {"daily_limit_usd": "10.00"}
    }
    
    result = cmd_dry_run("Test task")
    
    assert result == 0
```

#### Mock Environment Variables
```python
def test_valid_api_key(self, monkeypatch):
    """Test with mocked environment variable."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    
    result = validate_key("openrouter")
    
    assert result[0] is True
```

### Test Fixtures

#### Temporary Directories
```python
def test_config_creation(self, tmp_path):
    """Test with temporary directory."""
    config_file = tmp_path / "config.toml"
    
    cmd_init(config_path=config_file)
    
    assert config_file.exists()
```

#### Custom Fixtures
```python
@pytest.fixture
def mock_openrouter_key(monkeypatch):
    """Fixture for mocking OpenRouter API key."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    yield
    monkeypatch.delenv("OPENROUTER_API_KEY")
```

---

## Coverage Targets

### Critical Modules (Target: 85%+)
- `src/core/tier_manager.py` ✅ 98%
- `src/core/circuit_breaker.py` ✅ 94%
- `src/core/analytics.py` ✅ 92%
- `src/core/error_classifier.py` ✅ 91%
- `src/core/config.py` ✅ 100%
- `src/core/feedback.py` ✅ 100%
- `src/cli/main.py` ✅ 93%
- `src/cli/commands.py` ✅ 85%
- `src/providers/openai_provider.py` ✅ 89%
- `src/providers/anthropic_provider.py` ✅ 76%

### Important Modules (Target: 70%+)
- `src/core/cost.py` - 82%
- `src/core/metrics.py` - 84%
- `src/core/context_simplifier.py` - 72%
- `src/validators/api_keys.py` - 61%
- `src/validators/models.py` - 61%
- `src/validators/templates.py` - 52%

### Infrastructure Modules (Target: 60%+)
- `src/integrations/langchain_callback.py` - 30%
- `src/integrations/langchain_tools.py` - 27%
- `src/integrations/crewai_integration.py` - 31%
- `src/core/model_capabilities.py` - 45%
- `src/validators/startup.py` - 34%

### Future Modules (Target: 80%+)
- `src/core/orchestrator.py` - 30%
- `src/core/exceptions.py` - 0%
- `src/core/logging_config.py` - 0%
- `src/core/parallel.py` - 0%
- `src/core/prompt_format.py` - 0%
- `src/core/rate_limiter.py` - 0%
- `src/core/retry.py` - 0%
- `src/core/shutdown.py` - 0%

---

## Debugging Test Failures

### Common Issues

#### Import Errors
```python
# Error: ModuleNotFoundError
# Fix: Ensure path is added correctly
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
```

#### Mock Not Working
```python
# Error: AssertionError - Expected call not found
# Fix: Mock the correct import path
@patch('src.module.function')  # NOT @patch('module.function')
def test_with_mock(self, mock_func):
    ...
```

#### Fixture Scoping
```python
# Error: Fixture not available
# Fix: Use correct scope
@pytest.fixture(scope="function")  # or "class", "module", "session"
def my_fixture():
    ...
```

### Getting Test Output

```bash
# Capture stdout/stderr
pytest -s tests/unit/test_commands.py

# Show test duration
pytest --durations=10

# Show all output on failure
pytest -v --showlocals
```

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .[dev]
      
      - name: Run tests
        run: |
          pytest tests/ --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

### Coverage Report

```bash
# View HTML report
.venv/bin/python -m pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# View terminal report
.venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

## Test Maintenance

### Adding New Tests

1. **Identify Coverage Gap**
   - Run coverage analysis
   - Find untested code paths
   - Document test requirements

2. **Write Test**
   - Follow naming conventions
   - Use appropriate mocks
   - Add docstrings
   - Keep tests focused

3. **Verify**
   - Run test: `pytest tests/unit/test_<module>.py`
   - Check coverage: `--cov-report=term-missing`
   - Ensure all tests pass

### Updating Tests

1. **Refactor When Needed**
   - Extract common setup to fixtures
   - Use parameterized tests
   - Reduce code duplication

2. **Keep Tests Fast**
   - Avoid unnecessary I/O
   - Use mocks for external calls
   - Parallelize where possible

3. **Document Changes**
   - Update test descriptions
   - Add comments for complex logic
   - Update coverage expectations

---

## Performance Testing

### Benchmark Tests

```python
import time
from src.core.orchestrator import Orchestrator

def test_orchestrator_performance():
    """Test orchestrator execution time."""
    orchestrator = Orchestrator()
    
    start = time.time()
    result = orchestrator.execute("Test task")
    duration = time.time() - start
    
    assert duration < 5.0  # Should complete in under 5 seconds
    assert result.output is not None
```

### Load Testing

```python
import concurrent.futures

def test_concurrent_tasks():
    """Test handling multiple concurrent tasks."""
    orchestrator = Orchestrator()
    
    def run_task(i):
        return orchestrator.execute(f"Task {i}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_task, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    assert len(results) == 5
```

---

## Resources

### Documentation
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)

### Tools
- **pytest** - Test framework
- **pytest-cov** - Coverage reporting
- **pytest-xdist** - Parallel test execution
- **pytest-timeout** - Test timeout enforcement

### Contributing
- Read existing tests before adding new ones
- Follow established patterns
- Ensure 100% test pass rate
- Maintain or improve coverage

---

## Quick Reference

### Common Patterns

```python
# Import setup
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Environment variable setup
os.environ["KEY"] = "value"
# ... test ...
os.environ.pop("KEY", None)

# Mocking
@patch('module.function')
def test_func(self, mock_func):
    mock_func.return_value = "test"
    result = function()
    assert result == "test"

# Temporary files/directories
def test_with_temp_file(self, tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("content")
    assert file.exists()
```

### Useful Commands

```bash
# Fast feedback loop
pytest tests/unit/test_<module>.py -v

# Coverage check
pytest --cov=src --cov-report=term-missing | grep TOTAL

# Find tests
pytest tests/ --collect-only -q

# Run specific test
pytest tests/unit/test_<module>.py::TestClass::test_method

# Reset test environment
pytest --cache-clear
```

---

*Last Updated: April 28, 2026*  
*Test Suite Version: 1.0*  
*Overall Coverage: 58% (437 tests passing)*
