# Contributing to cost-orchestrator

Thank you for your interest in contributing to the cost-orchestrator project! This document provides guidelines and instructions for contributing.

## 🎯 Quick Start

### Setting Up Your Development Environment

```bash
# Clone the repository
git clone https://github.com/pairadmin/MR-Krabs
cd MR-Krabs

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
pytest tests/test_package.py -v
```

### Development Workflow

1. **Create a branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make your changes** following the code style guidelines below

3. **Run tests** to ensure everything works:
   ```bash
   pytest tests/ -v --cov=src --cov-report=term-missing
   ```

4. **Format and lint** your code:
   ```bash
   black src/ tests/
   ruff check src/ tests/
   mypy src/
   ```

5. **Commit** with clear messages:
   ```bash
   git commit -m "feat: add new feature description"
   # or
   git commit -m "fix: resolve issue with X"
   ```

6. **Push and create a PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

## 📋 Code Style Guidelines

### General Principles

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for all public functions, classes, and modules
- Keep functions focused and small (<50 lines when possible)
- Prefer readability over cleverness

### Type Hints

```python
from typing import Optional, List, Dict, Any
from decimal import Decimal

def calculate_cost(
    model_name: str,
    tokens: Dict[str, int],
    rate: Optional[Decimal] = None
) -> Decimal:
    """Calculate the cost for API usage."""
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def ask(prompt: str, budget: float = 10.0) -> AskResult:
    """Execute a prompt with cost optimization.
    
    This is the main entry point for LLM interactions.
    
    Args:
        prompt: The user prompt to send to the LLM.
        budget: Maximum daily budget in USD (default: 10.0).
    
    Returns:
        AskResult containing output, cost, and metadata.
    
    Raises:
        BudgetExceededError: If the daily budget is exceeded.
    
    Example:
        >>> result = ask("Write hello world")
        >>> print(result.output)
        >>> print(f"Cost: ${result.cost:.4f}")
    """
```

### Testing

- Write tests for all new features
- Maintain >85% code coverage
- Follow the existing test structure in `tests/`
- Name tests descriptively: `test_function_description_condition`

Example test:

```python
def test_calculate_cost_returns_decimal():
    """Test that calculate_cost returns a Decimal object."""
    tokens = {"prompt_tokens": 100, "completion_tokens": 200}
    cost = calculate_cost("gpt-3.5", tokens)
    assert isinstance(cost, Decimal)
    assert cost > 0
```

## 🧪 Running Tests

### All Tests

```bash
pytest tests/ -v
```

### With Coverage Report

```bash
pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
# Open htmlcov/index.html in browser for detailed coverage
```

### Specific Test File

```bash
pytest tests/test_cost.py -v
```

### Specific Test Function

```bash
pytest tests/test_cost.py::test_calculate_cost -v
```

### Test with Coverage Threshold

```bash
pytest tests/ --cov=src --cov-fail-under=85
```

## 📦 Building the Package

### Build Locally

```bash
# Install build tools
pip install build twine

# Build sdist and wheel
python -m build

# Check distribution with twine
twine check dist/*
```

### Test Installation

```bash
# Create a fresh virtual environment
python -m venv /tmp/test-env
source /tmp/test-env/bin/activate

# Install from local build
pip install dist/cost_orchestrator-0.1.0-py3-none-any.whl

# Verify installation
python -c "from cost_orchestrator import ask; print('Success!')"
```

## 🔍 Pre-Commit Hooks (Optional)

We use pre-commit hooks to automate code quality checks:

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## 🐛 Reporting Bugs

When reporting a bug, please include:

1. **Clear title** describing the issue
2. **Steps to reproduce** the problem
3. **Expected behavior** vs actual behavior
4. **Environment details**:
   - Python version
   - Operating system
   - Package version (`pip show cost-orchestrator`)
5. **Error messages** or stack traces (if applicable)
6. **Minimal reproducible example** if possible

## 💡 Feature Requests

For feature requests:

1. Open an issue with "feature" label
2. Describe the use case and problem you're solving
3. Suggest a potential solution or API design
4. Explain why this would benefit other users

## 🤝 Your First Contribution

Looking for your first issue to work on? Check out:

- Issues labeled **"good first issue"** - Simple tasks perfect for newcomers
- Issues labeled **"help wanted"** - Tasks that need community assistance
- Documentation improvements - Always welcome!

### Areas We Need Help With

- More unit tests (aiming for 90%+ coverage)
- Integration tests for CrewAI and LangChain
- Examples and tutorials in the docs
- Bug fixes and performance improvements
- Additional LLM provider integrations

## 🔄 Pull Request Process

1. **Fork the repository** and create your branch from `main`
2. **Make changes** following guidelines above
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Ensure all tests pass** and coverage requirements are met
6. **Submit PR** with clear description of changes
7. **Address review feedback** promptly

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Reference related issues in the PR description
- Include screenshots for UI changes (if applicable)
- Add examples demonstrating new features

## 📚 Resources

- [Project Documentation](https://github.com/pairadmin/MR-Krabs#readme)
- [Code of Conduct](CODE_OF_CONDUCT.md) (coming soon)
- [Development Guide](.github/CONTRIBUTING.md)
- [Test Coverage Report](TESTING_GUIDE.md)

## 🙏 Acknowledgments

Thank you for contributing to cost-orchestrator! Your contributions help make this tool better for everyone.

## 📞 Getting Help

If you need help or have questions:

- Open a GitHub issue
- Check existing documentation
- Review the codebase and examples

Happy coding! 🚀
