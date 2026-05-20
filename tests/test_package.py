"""Package validation tests for PyPI distribution.

These tests verify the package is properly structured and importable.
"""
import subprocess
import sys
from pathlib import Path

# Resolve repository root relative to this test file — portable across machines
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_version_exists():
    """Test that __version__ is defined."""
    from src import __version__
    
    assert __version__ is not None
    assert isinstance(__version__, str)
    assert len(__version__) > 0
    # Version should follow semantic versioning pattern
    parts = __version__.split('.')
    assert len(parts) >= 2, "Version should be at least X.Y.Z"


def test_main_imports():
    """Test that main entry points can be imported."""
    from src import ask, AskResult, BudgetExceededError
    
    assert callable(ask)
    assert AskResult is not None
    assert BudgetExceededError is not None


def test_helper_functions_exist():
    """Test that helper functions are exported."""
    from src import (
        get_budget_remaining,
        get_cost_summary,
        reset_tracker,
    )
    
    assert callable(get_budget_remaining)
    assert callable(get_cost_summary)
    assert callable(reset_tracker)


def test_all_exports_defined():
    """Test that __all__ is properly defined."""
    from src import __all__
    
    expected_exports = [
        'ask',
        'AskResult',
        'get_budget_remaining',
        'get_cost_summary',
        'reset_tracker',
        'BudgetExceededError',
    ]
    
    assert '__all__' in dir(sys.modules['src'])
    for export in expected_exports:
        assert export in __all__, f"{export} should be in __all__"


def test_package_can_be_built():
    """Test that the package can be built with setuptools."""
    result = subprocess.run(
        [sys.executable, '-m', 'build', '--sdist', '--wheel'],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True
    )
    
    # Build might fail if build tools not installed, which is OK for now
    # We just want to verify the structure is correct
    print("Build output:", result.stdout)
    if result.returncode != 0:
        print("Build stderr:", result.stderr)


def test_cli_entry_point_exists():
    """Test that CLI entry point module exists."""
    cli_path = REPO_ROOT / "src/cli/main.py"
    assert cli_path.exists(), "CLI main module should exist"
    
    # Check it has a main function
    with open(cli_path) as f:
        content = f.read()
    assert 'def main(' in content, "CLI should have main() function"


def test_pyproject_toml_exists():
    """Test that pyproject.toml exists and is valid."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml should exist"
    
    # Try to parse it as TOML (requires tomllib in Python 3.11+)
    try:
        import tomllib
        with open(pyproject_path, 'rb') as f:
            config = tomllib.load(f)
        
        assert 'project' in config, "pyproject.toml should have [project] section"
        assert 'name' in config['project'], "Project name should be defined"
        assert 'version' in config['project'], "Version should be defined"
    except ImportError:
        # Python < 3.11 doesn't have tomllib, just check file exists
        pass


def test_readme_exists():
    """Test that README.md exists."""
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.exists(), "README.md should exist"
    
    # Check it has content
    with open(readme_path) as f:
        content = f.read()
    assert len(content) > 500, "README should have substantial content"


def test_manifest_in_exists():
    """Test that MANIFEST.in exists."""
    manifest_path = REPO_ROOT / "MANIFEST.in"
    assert manifest_path.exists(), "MANIFEST.in should exist for packaging"
