# Contributing

## Quick Start

```bash
# Clone the repo
git clone https://github.com/pairadmin/orchestrator.git
cd orchestrator

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run linting
python -m ruff check src/ tests/
python -m black --check src/ tests/
```

## Project Structure

```
src/
  core/           # Core orchestration engine
  cli/            # CLI interface and subcommands
  validators/     # Startup validators
tests/
  unit/           # Unit tests
  e2e/            # End-to-end tests
  benchmarks/     # Performance benchmarks
docs/             # Documentation
templates/        # Prompt templates
examples/         # Example code
```

## Good First Issues

Look for issues labeled `good-first-issue` on GitHub. These are typically:
- Documentation improvements
- Adding test coverage for existing code
- Small bug fixes
- Adding new error classifications

## Code Style

- Follow PEP 8
- Use `black` for formatting (line length 100)
- Use `ruff` for linting
- Type hints required for all public APIs
- Docstrings for all public functions and classes

## Testing

- Write tests for all new functionality
- Run `pytest` before submitting PRs
- Benchmarks should not regress by more than 10%

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with a clear message
6. Push and open a PR

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
