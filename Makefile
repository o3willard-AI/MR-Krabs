.PHONY: dev test lint clean bench

dev:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	python3 -m pytest tests/ -v --cov=src --cov-report=term-missing

lint:
	python3 -m ruff check src/ tests/
	python3 -m black --check src/ tests/

format:
	python3 -m black src/ tests/

bench:
	python3 tests/benchmarks/test_benchmarks.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf build/ dist/ *.egg-info
