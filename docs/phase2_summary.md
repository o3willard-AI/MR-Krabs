# Phase 2: Framework Expansion - Summary Document

**Version**: 1.0  
**Date**: April 26, 2026  
**Duration**: Weeks 9-16 (8 weeks)  
**Status**: Planning Complete, Ready for Implementation

---

## Executive Summary

Phase 2 transforms MR-Krabs from a single-framework solution into a **comprehensive cost optimization layer** supporting multiple AI development frameworks. The phase focuses on:

1. **Framework Integration** - CrewAI (enhanced), LangChain, additional providers
2. **Context Optimization** - Automatic simplification on retry
3. **Provider Expansion** - OpenAI, Anthropic support
4. **Developer Experience** - Better docs, examples, CLI polish

---

## Phase 2 User Stories Overview

| Story | Priority | Estimate | Dependencies | Timeline |
|-------|----------|----------|--------------|----------|
| **P2-1: Enhanced CrewAI Integration** | P0 | 2 weeks | P1 complete | Weeks 9-10 |
| **P2-2: LangChain Integration** | P0 | 2 weeks | P2-1 | Weeks 11-12 |
| **P2-3: Context Simplification on Retry** | P1 | 1 week | P1-5 | Week 13 |
| **P2-4: Additional LLM Providers** | P1 | 1 week | P2-1, P2-2 | Week 14 |
| **P2-5: Advanced Analytics** | P2 | 1 week | P2-1 through P2-4 | Week 15 |
| **P2-6: Config Validation** | P2 | 0.5 weeks | All above | Week 16 |
| **P2-7: CLI Polish** | P2 | 0.5 weeks | All above | Week 16 |
| **P2-8: Documentation** | P2 | 1 week | All above | Week 16 |

**Total Estimated Effort**: 10 weeks (2 stories can be parallelized)

---

## Detailed Story Descriptions

### P2-1: Enhanced CrewAI Integration (2 weeks)

**Goal**: Seamless cost tracking for CrewAI workflows

**Key Features**:
- Automatic CrewAI tool costing
- Memory system compatibility
- Advanced tier mapping (agent role → tier)
- <5% performance overhead

**Deliverables**:
- `src/integrations/crewai_integration.py`
- `src/integrations/crewai_tools.py`
- Example: CrewAI project with cost tracking

**Acceptance**:
- ✅ CrewAI tools show cost in logs
- ✅ Memory workflows compatible
- ✅ <5% performance overhead verified

---

### P2-2: LangChain Integration (2 weeks)

**Goal**: Cost tracking for LangChain chains and agents

**Key Features**:
- Callback handler for all LangChain events
- Agent action tracking
- Tool cost aggregation
- LangSmith compatibility

**Deliverables**:
- `src/integrations/langchain_callback.py`
- `src/integrations/langchain_tools.py`
- Example: LangChain project with cost tracking

**Acceptance**:
- ✅ Callback handler tracks all events
- ✅ LangSmith integration verified
- ✅ Compatible with popular patterns

---

### P2-3: Context Simplification on Retry (1 week)

**Goal**: Automatic context reduction to improve success rates

**Key Features**:
- 100% → 70% → 40% → 20% context reduction
- Smart content removal (verbose, redundant, duplicates)
- Critical requirements preservation
- Integration with existing retry logic

**Deliverables**:
- `src/core/context_simplifier.py`
- Enhanced orchestrator retry logic

**Acceptance**:
- ✅ Success rate improvement >15%
- ✅ Critical requirements always preserved
- ✅ Logging of reduction methods

---

### P2-4: Additional LLM Providers (1 week)

**Goal**: Support OpenAI and Anthropic providers

**Key Features**:
- OpenAI provider adapter (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- Anthropic provider adapter (claude-3 family)
- Accurate pricing configuration
- Provider auto-detection

**Deliverables**:
- `src/providers/openai_provider.py`
- `src/providers/anthropic_provider.py`
- Extended pricing tables

**Acceptance**:
- ✅ Real API calls work with cost tracking
- ✅ Pricing accurate to official docs
- ✅ Same API surface as OpenRouter

---

### P2-5: Advanced Analytics (1 week)

**Goal**: Deeper insights into tier effectiveness and costs

**Key Features**:
- Success rates per tier
- Cost breakdown by tier/framework
- Tier effectiveness recommendations
- Provider comparison metrics

**Deliverables**:
- Enhanced `get_summary()` with tier analytics
- New CLI command: `orchestrator analytics`
- Dashboard-ready data structure

**Acceptance**:
- ✅ Success rates tracked per tier
- ✅ Cost breakdowns accurate
- ✅ Recommendations actionable

---

### P2-6: Config Validation & Migration (0.5 weeks)

**Goal**: Better configuration management

**Key Features**:
- Config validation on startup
- Migration tools from v1 to v2
- Clear error messages
- Deprecation warnings

**Deliverables**:
- Config validation module
- Migration scripts
- Updated CLI init wizard

**Acceptance**:
- ✅ Invalid config rejected with clear errors
- ✅ Migration tools work end-to-end
- ✅ Deprecation warnings helpful

---

### P2-7: CLI Polish (0.5 weeks)

**Goal**: Improved command-line experience

**Key Features**:
- Better error formatting
- Interactive hints
- Improved output readability
- Rich formatting for stats

**Deliverables**:
- Enhanced error output
- Better `orchestrator stats` display
- Improved `orchestrator doctor`

**Acceptance**:
- ✅ Error messages clear and actionable
- ✅ Output easy to read
- ✅ Rich formatting optional

---

### P2-8: Framework Documentation & Examples (1 week)

**Goal**: Comprehensive documentation for new features

**Key Features**:
- Framework-specific guides (CrewAI, LangChain)
- 5+ production examples
- Tutorial for new framework users
- Migration guides

**Deliverables**:
- `docs/crewai_integration.md`
- `docs/langchain_integration.md`
- `examples/crewai_cost_tracking/`
- `examples/langchain_cost_tracking/`

**Acceptance**:
- ✅ Framework guides complete
- ✅ 5+ production examples
- ✅ Tutorial works end-to-end

---

## Implementation Roadmap

```
Week 9-10: P2-1 (Enhanced CrewAI)
├── Week 9: Core integration, tool costing
├── Week 10: Memory compatibility, performance optimization

Week 11-12: P2-2 (LangChain Integration)
├── Week 11: Callback handlers, agent integration
├── Week 12: Tool support, examples

Week 13: P2-3 (Context Simplification)
└── Week 13: Context reduction logic, testing

Week 14: P2-4 (Additional Providers)
├── Week 14: OpenAI, Anthropic adapters

Week 15: P2-5 (Advanced Analytics)
└── Week 15: Success rates, tier effectiveness

Week 16: P2-6, P2-7, P2-8 (Polish & Docs)
├── Week 16a: Config validation, migration tools
├── Week 16b: CLI polish, error formatting
└── Week 16c: Framework documentation, examples
```

---

## Resource Requirements

### Engineering Team
- **Engineering Lead**: Full-time (8 weeks)
- **Software Engineer**: Full-time (8 weeks)
- **Framework Specialist**: Part-time (CrewAI + LangChain experts)

### Infrastructure
- **API Credits**: $300 (OpenAI, Anthropic, OpenRouter)
- **CI/CD**: Enhanced testing matrix
- **Testing**: Framework-specific test suites

### Community
- **CrewAI Maintainers**: Review integration
- **LangChain Maintainers**: Review callback handler
- **Community Feedback**: Discord, GitHub issues

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Framework API Changes** | Medium | High | Abstract layers, version tests |
| **Performance Overhead** | Low | Medium | Benchmarks, optimization sprints |
| **Integration Complexity** | Medium | Medium | Incremental approach, feedback |
| **Low Adoption** | Medium | High | Early adopters, clear value prop |
| **Maintenance Burden** | Medium | Medium | Community contributions, docs |

---

## Success Metrics

### Technical Metrics
- **Test Coverage**: 70% overall (up from 45%)
- **Framework Support**: 3+ frameworks
- **Performance**: <5% overhead
- **Success Rate**: >88% (up from 85%)

### Business Metrics
- **Cost Reduction**: 50% average (up from 40%)
- **GitHub Stars**: 500+ (up from 50+)
- **External Contributors**: 20+ (up from 5+)
- **Production Examples**: 5+ (up from 1)

### User Metrics
- **Setup Time**: <15 minutes
- **Documentation Rating**: >4/5
- **Framework Satisfaction**: >90%
- **Cost Savings**: >87% of premium-only

---

## Dependencies & Blockers

### Phase 2 Dependencies
```
P2-1 (CrewAI) ─┬─→ P2-5 (Analytics)
               ├─→ P2-8 (Docs)
P2-2 (LangChain)─┤
               ├─→ P2-5 (Analytics)
P2-3 (Context) ─┤
               ├─→ P2-5 (Analytics)
P2-4 (Providers)─┤
               └─→ P2-5 (Analytics)
P2-6 (Config) ──┴─→ P2-7 (CLI) → P2-8 (Docs)
```

### External Dependencies
- CrewAI framework updates
- LangChain framework updates
- API provider availability
- Community feedback channels

---

## Definition of Done

### For Each Story
- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Documentation updated
- [ ] Example project included
- [ ] Code reviewed
- [ ] No breaking changes

### For Phase 2
- [ ] All 8 stories complete
- [ ] End-to-end testing successful
- [ ] Performance benchmarks verified
- [ ] Documentation comprehensive
- [ ] Community feedback positive
- [ ] Ready for production release

---

## Next Steps

### Immediate (This Week)
1. **Stakeholder Review** - Validate Phase 2 plan
2. **Resource Allocation** - Assign team members
3. **Setup Environment** - API keys, test frameworks
4. **Start P2-1** - Begin CrewAI integration

### First Sprint (Weeks 9-10)
1. **P2-1 Completion** - CrewAI integration done
2. **Early Feedback** - Share with CrewAI community
3. **Benchmarks** - Verify <5% overhead
4. **Documentation** - CrewAI guide draft

### Ongoing
1. **Weekly Reviews** - Progress against plan
2. **Community Engagement** - Feedback loops
3. **Quality Gates** - Code review, testing
4. **Documentation** - Continuous updates

---

## Open Questions

1. **Additional Providers**: Should we add Google Vertex AI or AWS Bedrock?
2. **Real-time Monitoring**: Is web dashboard needed before Phase 3?
3. **Framework Optimization**: Should we prioritize specific frameworks?
4. **Community Strategy**: How to engage framework maintainers?

---

## Appendix

### A. Story Card Links
- [P2-1: Enhanced CrewAI Integration](./user_stories/P2-1_CREWAII_INTEGRATION.md)
- [P2-2: LangChain Integration](./user_stories/P2-2_LANGCHAIN_INTEGRATION.md)
- [P2-3: Context Simplification](./user_stories/P2-3_CONTEXT_SIMPLIFICATION.md)
- [P2-4: Additional Providers](./user_stories/P2-4_ADDITIONAL_PROVIDERS.md)

### B. Implementation Roadmap
- [Full Roadmap](../IMPLEMENTATION_ROADMAP.md)

### C. Phase 1 Completion
- [Phase 1 Complete Report](../PHASE1_COMPLETE.md)

---

*Draft: April 26, 2026*  
*Status: Ready for Stakeholder Review*
