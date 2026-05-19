# MR-Krabs Grafana Dashboards

## Overview Dashboard

**File:** `mrkrabs-overview.json`
**Import:** Grafana → Dashboards → Import → Upload JSON file

### Panels
1. **Cost Rate** — Real-time spend rate by provider/model
2. **Budget Remaining** — Gauge showing daily budget remaining with color zones (red < $2, orange $2-5, yellow $5-8, green $8+)
3. **Request Latency** — P50/P95/P99 latency by tier
4. **Error Rate** — Error frequency by type and provider
5. **Tier Escalations** — Escalation frequency between tiers

### Prerequisites
- Prometheus server scraping `http://<mrkrabs-host>:8001/metrics`
- Grafana with Prometheus datasource configured
