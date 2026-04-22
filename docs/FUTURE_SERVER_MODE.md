# Future: Server Mode (Out of Scope for v1)

**Status**: Future / Out of Scope
**Created**: 2026-04-03
**Decision**: Separate project or distinct `cost-orchestrator-server` package

---

## Overview

This document captures server-mode and platform ambitions that are explicitly **out of scope** for the v1 library. The core product is a pip-installable Python library. Everything below is a future consideration.

## What Is Out of Scope

### Web Dashboard
- React-based cost visualization dashboard
- Real-time task monitoring UI
- Team management interface

### Multi-Tenant Architecture
- User accounts and authentication
- Organization/team isolation
- Role-based access control

### Distributed Infrastructure
- Docker containers and Docker Compose
- Kubernetes Helm charts
- Load balancers (nginx/traefik)
- PostgreSQL as shared database
- Redis for caching/queuing
- RabbitMQ for message brokering

### FastAPI REST API Server
- HTTP endpoints for orchestration
- API authentication and rate limiting
- Multi-instance deployment

### ML-Powered Optimization
- ML-based tier assignment models
- Federated learning across users
- Predictive cost modeling

### SaaS Offering
- Hosted multi-tenant service
- Billing and subscription management

## Rationale

The Architecture Review (REVIEW_ARCHITECTURE_2026-04-03.md, §2.1) identified a critical identity crisis: the project describes itself as a "free, open-source Python library" but the architecture includes Docker, Kubernetes, PostgreSQL, Redis, RabbitMQ, FastAPI, React dashboard, and multi-tenant architecture.

These are two different products:
- **Product A**: A pip-installable Python library (`pip install cost-orchestrator`)
- **Product B**: A self-hosted observability and orchestration platform

Building both simultaneously means neither gets adequate attention. Library users don't want Docker. Platform users need full infrastructure.

## What v1 Is

A pip-installable Python library that:
- Routes LLM tasks to cheaper models first, escalates when needed
- Tracks costs with local SQLite/JSON storage
- Enforces budgets with atomic reservation patterns
- Provides a CLI for setup, diagnostics, and cost reports
- Integrates with CrewAI, LangChain, and standalone Python code

Zero infrastructure dependencies. No Docker. No database server. No web UI.

## When to Revisit

Server mode should be considered only after:
1. The library has 1,000+ active users
2. Clear demand for team/multi-user features
3. The library API is stable and well-tested
4. A separate team or dedicated resources are available

## If Built, How

As a separate package: `cost-orchestrator-server`
- Depends on the core library
- Adds FastAPI, PostgreSQL, Redis, React frontend
- Separate versioning, separate release cycle
- Clear boundary: server mode wraps the library, doesn't replace it

## References

- Architecture Review §2.1: Identity Crisis
- Architecture Review §Q10: "Separate the library from the server"
- DX Review §5.4: Proxy Mode (alternative path for zero-code integration)
