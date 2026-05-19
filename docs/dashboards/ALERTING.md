# MR-Krabs Alerting Guide

## Overview

MR-Krabs exposes Prometheus metrics and alert rules for proactive budget monitoring and error detection.

## Alert Rules

### BudgetWarning
- **Severity:** warning
- **Threshold:** Budget < 20%
- **Response:** Routing downgraded to cost_aware. No blocking.
- **Recovery:** Budget increases above 20% (daily reset or manual increase).

### BudgetCritical
- **Severity:** critical
- **Threshold:** Budget < 10%
- **Response:** L2+ tiers blocked. Only L0-L1 allowed.
- **Recovery:** Increase budget via `mrkrabs budget set <amount>` or wait for daily reset.

### BudgetExhausted
- **Severity:** critical
- **Threshold:** Budget ≤ $0
- **Response:** All ask() calls blocked. `/health` still returns 200 with budget_exhausted: true.
- **Recovery:** Increase budget or wait for midnight UTC reset.

### HighErrorRate
- **Severity:** warning
- **Threshold:** Error rate > 5% over 5 minutes
- **Response:** Investigate provider health, check circuit breaker status.
- **Recovery:** Error rate drops below threshold for 5 minutes.

### EscalationSpiral
- **Severity:** warning
- **Threshold:** > 5 escalations/minute for 2 minutes
- **Response:** Check for model outages. Consider temporarily disabling affected tiers.
- **Recovery:** Escalation rate returns to normal.

### AdapterUnhealthy
- **Severity:** critical
- **Threshold:** Any adapter DOWN for 2 minutes
- **Response:** Check adapter logs. Restart if needed.
- **Recovery:** Adapter returns to HEALTHY status.

## Configuring Alertmanager

1. Add the alert rules to your Prometheus config:
```yaml
rule_files:
  - "/etc/prometheus/mrkrabs_alerts.yml"
```

2. Configure Alertmanager routing:
```yaml
route:
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack'
```

## Testing Alerts

Simulate budget exhaustion:
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_budget_check \
  -H "Content-Type: application/json" \
  -d '{"would_spend": 999.99}'
```

## Silence / Maintenance

To silence alerts during maintenance:
```bash
# Via Alertmanager API
curl -X POST http://alertmanager:9093/api/v2/silences \
  -H "Content-Type: application/json" \
  -d '{"matchers":[{"name":"service","value":"mrkrabs","isRegex":false}],"startsAt":"...","endsAt":"...","comment":"Maintenance window"}'
```
