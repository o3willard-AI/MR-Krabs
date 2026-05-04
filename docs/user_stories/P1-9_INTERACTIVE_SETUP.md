# Story P1-9: Interactive Setup Wizard

**Priority**: P1 (High)  
**Estimate**: 2 days  
**Phase**: Week 2

---

## User Story

As a new developer  
I want a guided setup wizard  
So that I can configure the orchestrator in <5 minutes instead of 30+ minutes

---

## Acceptance Criteria

### AC1: Wizard Flow
- [ ] `orchestrator init` launches interactive wizard
- [ ] Step 1: API key input (hidden/secure)
- [ ] Step 2: Budget configuration (default + override)
- [ ] Step 3: Optional LM Studio setup
- [ ] Step 4: Quick test of API key
- [ ] Progress indicator showing current step

### AC2: Smart Defaults
- [ ] Pre-fills reasonable defaults (e.g., $10/day budget)
- [ ] Press Enter to accept default
- [ ] Type custom value to override
- [ ] Shows validation errors inline

### AC3: Immediate Validation
- [ ] Tests API key immediately after input
- [ ] Shows success/failure for each test
- [ ] If API key invalid, offers to re-enter
- [ ] If LM Studio unreachable, warns but allows continuing

### AC4: Config File Generation
- [ ] Generates `~/.cost_orchestrator.toml`
- [ ] Format matches Story P1-8 schema
- [ ] Includes comment header with timestamp
- [ ] File permissions: 600 (owner read/write only)

### AC5: UX Requirements
- [ ] Clear prompts with examples
- [ ] Shows current values with [default] notation
- [ ] Success indicators (✓ green checkmarks)
- [ ] Error messages with actionable next steps
- [ ] Can skip optional steps

---

## Technical Implementation

### Files to Modify
1. `src/cli/commands.py` - `cmd_init()` implementation

### Implementation Notes
- Already started in Story P1-4
- Add real API key validation
- Add file permissions setting
- Add progress bar

---

## Testing Requirements

### Unit Tests
1. `test_init_creates_config` - Config file created
2. `test_init_validates_api_key` - Invalid key rejected
3. `test_init_uses_defaults` - Pressing Enter accepts defaults
4. `test_init_writes_secure_perms` - File permissions 600

### Integration Tests
1. Full wizard flow with valid API key
2. Wizard flow with invalid API key (re-enter)
3. Wizard flow skipping LM Studio

---

## Out of Scope
- Config file encryption
- Multiple profiles
- Cloud backup of config

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Wizard completes in <5 minutes
- [ ] Config file valid and working
- [ ] Code reviewed and approved
