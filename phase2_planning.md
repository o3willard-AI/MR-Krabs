# Phase 2 Planning: Framework Expansion

**Version**: 1.0  
**Date**: April 26, 2026  
**Phase Duration**: Weeks 9-16 (8 weeks)  
**Priority**: Framework Coverage & Enhanced Features

---

## Executive Summary

Phase 2 expands MR-Krabs from a single-framework solution to a **multi-framework orchestration layer**. The goal is to support 3+ major AI development frameworks while maintaining the core value proposition: **cost optimization with zero configuration**.

### Phase 2 Goals

1. **Framework Coverage** - Support CrewAI (enhanced), LangChain, and 1 additional framework
2. **Enhanced Features** - Context simplification, advanced analytics, better error handling
3. **Improved UX** - Better configuration, CLI polish, developer experience
4. **Community Building** - Open source contributions, documentation, framework partnerships

### Success Metrics

| Metric | Phase 1 | Phase 2 Target |
|--------|---------|----------------|
| **Cost Reduction** | 40% | 50% |
| **Success Rate** | >85% | >88% |
| **Framework Coverage** | 1 (CrewAI) | 3+ frameworks |
| **GitHub Stars** | 50+ | 500+ |
| **External Contributors** | 5+ | 20+ |
| **Test Coverage** | 45% | 70% |
| **Production Examples** | 1 | 5+ |

---

## Phase 2 User Stories

### P2-1: Enhanced CrewAI Integration
**Priority**: P0 (Critical)  
**Estimate**: 2 weeks  
**Dependencies**: P1 complete

### P2-2: LangChain Integration
**Priority**: P0 (Critical)  
**Estimate**: 2 weeks  
**Dependencies**: P2-1

### P2-3: Context Simplification on Retry
**Priority**: P1 (High)  
**Estimate**: 1 week  
**Dependencies**: P1-5 (budget warnings)

### P2-4: Additional LLM Providers
**Priority**: P1 (High)  
**Estimate**: 1 week  
**Dependencies**: P2-1, P2-2

### P2-5: Advanced Analytics & Success Rates
**Priority**: P2 (Medium)  
**Estimate**: 1 week  
**Dependencies**: P2-1 through P2-4

### P2-6: Configuration Validation & Migration Tools
**Priority**: P2 (Medium)  
**Estimate**: 0.5 weeks  
**Dependencies**: P2-1 through P2-5

### P2-7: CLI Polish & Developer Experience
**Priority**: P2 (Medium)  
**Estimate**: 0.5 weeks  
**Dependencies**: P2-1 through P2-6

### P2-8: Framework Documentation & Examples
**Priority**: P2 (Medium)  
**Estimate**: 1 week  
**Dependencies**: P2-1 through P2-7

---

## Implementation Timeline

```
Week 9-10: Enhanced CrewAI Integration (P2-1)
├── Week 9: Core integration, tool costing
├── Week 10: Memory compatibility, performance optimization

Week 11-12: LangChain Integration (P2-2)
├── Week 11: Callback handlers, agent integration
├── Week 12: Tool support, examples

Week 13: Context Simplification (P2-3)
└── Week 13: Context reduction logic, testing

Week 14: Additional Providers (P2-4)
├── Week 14: OpenAI, Anthropic adapters

Week 15: Advanced Analytics (P2-5)
├── Week 15: Success rate tracking, tier effectiveness

Week 16: Polish & Documentation (P2-6, P2-7, P2-8)
├── Week 16: Config validation, CLI polish, examples
```

---

## Resource Requirements

### Engineering
- **Engineering Lead**: Full-time (8 weeks)
- **Software Engineer**: Full-time (8 weeks)
- **Framework Specialist**: Part-time (CrewAI + LangChain maintainers)

### Testing
- Access to CrewAI, LangChain, OpenAI, Anthropic APIs for testing
- CI/CD integration with framework testing suites

### Community
- Engagement with framework maintainers (CrewAI, LangChain)
- Community feedback loops during development

---

## Risk Management

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Framework API instability | Medium | High | Abstract integration layers, version tests |
| Integration complexity | Medium | Medium | Incremental approach, user feedback |
| Performance overhead | Low | Medium | Continuous benchmarking, optimization |
| Low framework adoption | Medium | High | Demonstrate clear value, early adopters |
| Maintenance burden | Medium | Medium | Community contributions, clear abstractions |

---

## Dependencies & Blockers

### Phase 2 Dependencies
- **P2-1** must complete before **P2-2** (framework integration patterns)
- **P2-3** depends on **P1-5** (budget warning infrastructure)
- **P2-5** requires data from **P2-1** through **P2-4** (analytics need usage data)
- **P2-6** through **P2-8** depend on all feature stories

### External Dependencies
- Framework maintainer approvals (optional but recommended)
- API access for testing (CrewAI, LangChain, OpenAI, Anthropic)
- Community feedback channels (GitHub issues, Discord, forums)

---

## Acceptance Criteria Summary

### P2-1: Enhanced CrewAI
- ✅ CrewAI tools show cost in logs
- ✅ Memory workflows compatible
- ✅ <5% performance overhead

### P2-2: LangChain Integration
- ✅ Existing apps add cost tracking with callbacks
- ✅ Tools show cost in LangSmith traces
- ✅ Compatible with popular patterns

### P2-3: Context Simplification
- ✅ Retry with 100% → 70% → 40% context reduction
- ✅ Improves success rates on complex tasks
- ✅ Maintains task integrity

### P2-4: Additional Providers
- ✅ OpenAI and Anthropic adapters
- ✅ Same API surface as OpenRouter
- ✅ Pricing configured accurately

### P2-5: Advanced Analytics
- ✅ Success rates per tier
- ✅ Cost breakdown by tier/framework
- ✅ Tier effectiveness recommendations

### P2-6: Config Validation
- ✅ Migration tools from v1 to v2
- ✅ Validation on startup
- ✅ Clear error messages

### P2-7: CLI Polish
- ✅ Better error formatting
- ✅ Interactive hints
- ✅ Improved output readability

### P2-8: Documentation
- ✅ Framework-specific guides
- ✅ 5+ production examples
- ✅ Tutorial for new framework users

---

## Next Steps

1. **Review** - Stakeholder review of Phase 2 stories
2. **Refine** - Adjust estimates based on team capacity
3. **Start P2-1** - Begin enhanced CrewAI integration
4. **Engage Community** - Announce Phase 2 plans, gather feedback

---

## Open Questions

1. Should we add **Google Vertex AI** or **AWS Bedrock** in Phase 2?
2. Is **real-time cost monitoring** needed before Phase 3?
3. Should **framework-specific optimizations** be prioritized?
4. What **community engagement** strategy for framework launches?

---

*Draft: April 26, 2026*
