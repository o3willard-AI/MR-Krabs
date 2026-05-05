# P5-5: PyPI Package Creation

## Overview
Prepare and publish the cost-orchestrator package to PyPI for community distribution and easy installation via `pip install cost-orchestrator`.

## Background
The project has completed Phases 1-4 with:
- Fully implemented core functionality
- 742 passing tests at 67% coverage
- Comprehensive README with migration guides
- Clean git repository ready for release

Users currently need to clone and install manually. PyPI packaging will enable:
- `pip install cost-orchestrator` one-line installation
- Version management and releases
- Community adoption and discoverability
- Automated dependency management

## User Story
**As a** developer evaluating cost optimization tools  
**I want** to install the package via pip  
**So that** I can quickly integrate it into my projects without manual setup

## Acceptance Criteria

### AC1: PyPI Package Metadata Setup
- [ ] `pyproject.toml` contains complete package metadata:
  - Name: `cost-orchestrator`
  - Version: `1.0.0`
  - Description: "Zero-config, cost-saving LLM orchestration with auto-escalation and budget tracking"
  - Long description from README.md
  - Authors: "o3willard <o3willard@yahoo.com>"
  - License: "MIT"
  - Keywords: ["LLM", "cost-optimization", "orchestration", "budget-tracking", "AI"]
  - Classifiers: Python versions, license, development status
- [ ] `MANIFEST.in` includes all necessary files
- [ ] Package structure is correct (`src/layout.py`)

### AC2: Build & Test Locally
- [ ] `pip install build` and `python -m build` succeeds
- [ ] `pip install twine` and `twine check dist/*` passes validation
- [ ] Test installation from built wheel:
  ```bash
  pip install dist/cost_orchestrator-1.0.0-py3-none-any.whl
  python -c "from cost_orchestrator import ask; print('Import successful')"
  ```
- [ ] All entry points work (CLI commands: `orchestrator --help`)

### AC3: TestPyPI Upload & Verification
- [ ] Create TestPyPI account (test.pypi.org)
- [ ] Configure `.pypirc` or use `twine upload --repository testpypi`
- [ ] Upload to TestPyPI successfully
- [ ] Test installation from TestPyPI:
  ```bash
  pip install --index-url https://test.pypi.org/simple/ cost-orchestrator
  ```
- [ ] Verify package works with TestPyPI installation

### AC4: Production PyPI Upload
- [ ] Create PyPI account (pypi.org)
- [ ] Verify package name `cost-orchestrator` is available
- [ ] Upload to production PyPI:
  ```bash
  twine upload dist/*
  ```
- [ ] Verify package is publicly accessible at https://pypi.org/project/cost-orchestrator
- [ ] Test fresh installation:
  ```bash
  pip install cost-orchestrator
  orchestrator --help
  ```

### AC5: Release Documentation
- [ ] Update README badge section with PyPI version badge
- [ ] Create GitHub release v1.0.0 with changelog
- [ ] Add installation instructions:
  ```
  pip install cost-orchestrator
  ```
- [ ] Tag repository: `git tag v1.0.0 && git push origin v1.0.0`

## Implementation Plan

### Phase 1: Package Metadata (1-2 hours)
1. **Update `pyproject.toml`:**
   ```toml
   [project]
   name = "cost-orchestrator"
   version = "1.0.0"
   description = "Zero-config, cost-saving LLM orchestration with auto-escalation and budget tracking"
   readme = "README.md"
   authors = [{name = "o3willard", email = "o3willard@yahoo.com"}]
   license = {text = "MIT"}
   keywords = ["LLM", "cost-optimization", "orchestration", "budget", "AI"]
   classifiers = [
       "Development Status :: 4 - Beta",
       "Intended Audience :: Developers",
       "License :: OSI Approved :: MIT License",
       "Programming Language :: Python :: 3.11",
       "Programming Language :: Python :: 3.12",
       "Topic :: Software Development :: Libraries :: Python Modules",
   ]
   requires-python = ">=3.11"
   dependencies = [
       "openai>=1.0.0",
       "pydantic>=2.0",
       "rich>=13.0",
       # ... other dependencies
   ]

   [project.optional-dependencies]
   dev = [
       "pytest>=7.0",
       "pytest-cov>=4.0",
       "hypothesis>=6.0",
   ]
   crewai = ["crewai>=0.10.0"]
   langchain = ["langchain-core>=0.1.0", "langchain>=0.1.0"]

   [project.scripts]
   orchestrator = "src.cli.main:main"

   [build-system]
   requires = ["setuptools>=61.0", "wheel"]
   build-backend = "setuptools.build_meta"
   ```

2. **Create `MANIFEST.in`:**
   ```
   include README.md
   include LICENSE
   include docs/*.md
   include docs/user_stories/*.md
   recursive-include src *.py
   recursive-include tests *.py
   global-exclude *.pyc
   global-exclude __pycache__
   ```

3. **Add LICENSE file** (MIT license text)

### Phase 2: Local Build & Test (1-2 hours)
1. **Install build tools:**
   ```bash
   pip install build twine
   ```

2. **Build package:**
   ```bash
   python -m build
   ```
   Expected output: `dist/cost_orchestrator-1.0.0-*.tar.gz` and `dist/cost_orchestrator-1.0.0-*.whl`

3. **Validate package:**
   ```bash
   twine check dist/*
   ```

4. **Test installation:**
   ```bash
   pip install --force-reinstall dist/cost_orchestrator-1.0.0-*.whl
   python -c "import cost_orchestrator; print('✓ Package imported')"
   orchestrator --help
   ```

### Phase 3: TestPyPI Upload (30 minutes)
1. **Create TestPyPI account:**
   - Visit https://test.pypi.org/
   - Sign up with GitHub account

2. **Create API token:**
   - Go to Accounts → API Tokens
   - Generate token with full access

3. **Upload to TestPyPI:**
   ```bash
   twine upload --repository testpypi dist/*
   # Enter username: __token__
   # Enter password: <your-testpypi-token>
   ```

4. **Test TestPyPI installation:**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ cost-orchestrator
   python -c "from cost_orchestrator import ask; print('✓ TestPyPI installation works')"
   ```

### Phase 4: Production PyPI Upload (30 minutes)
1. **Create PyPI account:**
   - Visit https://pypi.org/
   - Sign up with GitHub or email

2. **Verify package name availability:**
   - Search https://pypi.org/search/?q=cost-orchestrator
   - Ensure name is available (if not, consider `cost-optimized-orchestrator`)

3. **Create PyPI API token:**
   - Go to Account → API Tokens
   - Generate token with full access
   - Use `__token__` as username

4. **Upload to PyPI:**
   ```bash
   twine upload dist/*
   # Enter username: __token__
   # Enter password: <your-pypi-token>
   ```

5. **Verify publication:**
   - Visit https://pypi.org/project/cost-orchestrator/
   - Check "Files" tab for uploaded distributions
   - Test fresh installation

### Phase 5: Release Documentation (1 hour)
1. **Update README badges:**
   ```markdown
   [![PyPI version](https://badge.fury.io/py/cost-orchestrator.svg)](https://pypi.org/project/cost-orchestrator/)
   [![Python Version](https://img.shields.io/pypi/pyversions/cost-orchestrator.svg)](https://pypi.org/project/cost-orchestrator/)
   ```

2. **Create GitHub release:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
   - Go to GitHub Releases → "Draft new release"
   - Tag: v1.0.0
   - Title: "Version 1.0.0 - Cost-Optimized AI Orchestrator"
   - Body: Include changelog and breaking changes

3. **Update documentation:**
   - Add "Installation" section with PyPI instructions
   - Update "Version" in documentation
   - Link to PyPI package page

## Testing Requirements

### Unit Tests
- [ ] `test_pypi_build` - Verify package builds successfully
- [ ] `test_pypi_metadata` - Validate package metadata
- [ ] `test_cli_entry_point` - Confirm CLI commands work after installation

### Integration Tests
- [ ] `test_installation_from_pypi` - Test actual PyPI installation
- [ ] `test_import_after_install` - Verify all imports work
- [ ] `test_functionality_after_install` - Run basic functionality test

## Metrics
- Package size < 10MB (target: 2-5MB)
- Installation time < 30 seconds
- All imports resolve correctly
- CLI entry point available system-wide

## Dependencies
- **Required**: openai, pydantic, rich, toml
- **Optional**: crewai, langchain-core, langchain

## Notes
- Use semantic versioning (v1.0.0 for first production release)
- Consider pre-release tags (v0.9.0-beta) if testing needed
- PyPI package name must be unique (check availability first)
- Include CHANGELOG.md in package for release notes

## References
- PyPI packaging guide: https://packaging.python.org/
- Twine documentation: https://pypi.org/help/#quick-upload
- TestPyPI: https://test.pypi.org/

---

## Priority: HIGH
**Target Date:** Upon successful GitHub push
**Estimated Effort:** 4-6 hours total
**Dependencies:** P5-2 (Code Cleanup) - ✅ COMPLETE
