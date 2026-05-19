# Story P3-0a: Dependency Audit & Compatibility Report

**Priority:** P0 (Critical — blocks all integration work)
**Estimate:** 3 days
**Phase:** Phase 0 — Week 1

---

## User Story

As a **developer** integrating LiteLLM components into MR-Krabs,
I want a comprehensive dependency audit comparing both projects' requirements
So that I can identify conflicts, version constraints, and compatibility issues before any code is forked.

---

## Acceptance Criteria

### AC1: Full Dependency Matrix
- [ ] Extract all runtime dependencies from MR-Krabs `pyproject.toml`
- [ ] Extract all runtime dependencies from LiteLLM's `pyproject.toml` / `setup.py` / `requirements.txt`
- [ ] Generate a comparison matrix with these columns:
  - Package name, MR-Krabs version, LiteLLM version, Conflict? (yes/no), Resolution
- [ ] Flag semantic-version conflicts (e.g., pydantic v1 vs v2)
- [ ] Identify transitive dependency overlaps and their constraints

### AC2: Conflict Resolution Plan
- [ ] For each conflict, propose one of: pin-to-version, upgrade-mrkrabs, fork-locally, or skip-component
- [ ] Verify no `pip install` deadlock across ALL Phase 0–5 combined requirements
- [ ] Document minimum Python version required by combined dependency set

### AC3: Compatibility Report Artifact
- [ ] Produce `docs/integration/compatibility_report.md` with:
  - Executive summary (green/yellow/red for each phase)
  - Full dependency matrix table
  - Recommended `pyproject.toml` additions with version pins
  - Risk register: what could break if versions drift
- [ ] Report must pass: `pip-compile --generate-hashes` succeeds on combined constraint set

### AC4: Security Scan
- [ ] Run `pip-audit` on both current dependency trees independently
- [ ] Run `pip-audit` on the proposed combined dependency tree
- [ ] Zero HIGH or CRITICAL vulnerabilities in combined tree
- [ ] Document any MEDIUM findings with mitigation timeline

---

## Technical Notes

- Use `pipdeptree` or `pipgrip` to visualize dependency trees
- LiteLLM source lives at `github.com/BerriAI/litellm` — clone at specific release tag, not `main`
- Pay special attention to: `pydantic`, `openai`, `httpx`, `anyio` — these are the most likely conflict points
- Integration scope is adapter-based, not full fork — only components listed in the strategy document need resolution

---

## Definition of Done

- [ ] Compatibility report committed to `docs/integration/compatibility_report.md`
- [ ] `pip-compile` succeeds on merged constraint set
- [ ] `pip-audit` returns zero HIGH/CRITICAL
- [ ] Peer review by one other developer
