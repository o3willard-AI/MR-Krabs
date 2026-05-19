# Story P3-1c: Budget Alert Monitoring Rules

**Priority:** P0 (Critical — customers must know before they overspend)
**Estimate:** 2 days
**Phase:** Phase 1 — Week 3

---

## User Story

As an **operator** managing MR-Krabs in production,
I want Prometheus alerting rules that fire BEFORE budget thresholds are breached
So that I have time to react — increase budget, investigate runaway costs, or pause operations.

---

## Acceptance Criteria

### AC1: Prometheus Alert Rules
- [ ] Create `docs/dashboards/mrkrabs_alerts.yml` — Prometheus alert rules file:
  - `BudgetWarning` — fires when `mrkrabs_budget_remaining_dollars < 20%` of daily limit
    - Severity: `warning`
    - Summary: "MR-Krabs daily budget at {{ $value }}% remaining"
  - `BudgetCritical` — fires when `mrkrabs_budget_remaining_dollars < 10%` of daily limit
    - Severity: `critical`
    - Summary: "MR-Krabs daily budget critically low: {{ $value }}% remaining"
  - `BudgetExhausted` — fires when `mrkrabs_budget_remaining_dollars <= 0`
    - Severity: `critical`
    - Summary: "MR-Krabs daily budget EXHAUSTED — all requests blocked"
  - `HighErrorRate` — fires when error rate > 10% over 5 minutes
    - Severity: `warning`
    - Summary: "MR-Krabs error rate {{ $value }}% (threshold: 10%)"
  - `EscalationSpiral` — fires when > 5 escalations/minute (indicates tasks failing at all tiers)
    - Severity: `warning`
    - Summary: "MR-Krabs escalation rate {{ $value }}/min — possible model outage"
  - `AdapterUnhealthy` — fires when any adapter health check returns DOWN
    - Severity: `critical`
    - Summary: "MR-Krabs adapter {{ $labels.adapter }} is DOWN"

### AC2: Alertmanager Integration
- [ ] Alert routing configuration in same file:
  - `warning` → Slack/Discord webhook (non-paging)
  - `critical` → PagerDuty/OpsGenie + Slack/Discord
  - All alerts → email digest (bundled every 15 min)
- [ ] Webhook URLs configurable via environment variables, never hardcoded
- [ ] Template webhook payloads documented

### AC3: Budget-Aware Auto-Response
- [ ] When `BudgetWarning` fires, MR-Krabs MCP server automatically:
  - Logs `[BUDGET WARNING]` with current spend, remaining, and projected exhaustion time
  - Downgrades routing strategy to `cost_aware` if currently using `smart` or `latency_aware`
  - Continues serving requests (does not block)
- [ ] When `BudgetCritical` fires:
  - Blocks L2+ tier requests (allows only L0-L1)
  - Returns `429 Too Many Requests` with `X-Budget-Status: critical` header for blocked tiers
- [ ] When `BudgetExhausted` fires:
  - All `ask()` calls return error immediately — no API call made
  - `/health` endpoint still returns 200 but includes `budget_exhausted: true`

### AC4: Dashboard Integration
- [ ] Budget panel in Grafana shows colored zones: green (>50%), yellow (20-50%), orange (10-20%), red (<10%)
- [ ] Alert firing indicator on dashboard (red dot on affected panels)
- [ ] Budget "burn rate" gauge — extrapolates current rate to predict exhaustion time

### AC5: Documentation
- [ ] `docs/dashboards/ALERTING.md`:
  - How to configure Alertmanager
  - Webhook setup for Slack, Discord, PagerDuty
  - Testing alerts: `curl -X POST /test-alert?severity=critical`
  - Silence/maintenance window instructions
  - Runbook: what to do for each alert type

---

## Technical Notes

- Alert rules use PromQL expressions referencing `mrkrabs_*` metrics from P3-1a
- Threshold values (20%, 10%) should be configurable via `[litellm.metrics]` TOML section
- Auto-response logic in `src/metrics/budget_alerter.py` — polls Prometheus metrics internally, no Prometheus server dependency for the auto-response feature
- Cooldown: alerts re-fire after 5 min by default (`repeat_interval: 5m`)
- All alert rules include `runbook_url` annotation pointing to the relevant section of ALERTING.md

---

## Definition of Done

- [ ] `docs/dashboards/mrkrabs_alerts.yml` committed with all 6 alert rules
- [ ] Budget auto-response logic implemented and tested
- [ ] Grafana dashboard updated with budget zones and alert indicators
- [ ] `docs/dashboards/ALERTING.md` complete with runbooks
- [ ] Test: simulate budget exhaustion → verify `ask()` returns error, `/health` reports correctly
- [ ] Test: simulate high error rate → verify alert fires, webhook payload valid
