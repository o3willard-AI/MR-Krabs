# P2-4: Context Simplification on Retry

**Priority:** P1 (Important)  
**Estimate:** 2 days (Week 15)  
**User Story:** As a developer, I want failed tasks to automatically retry with simplified context so I get higher success rates without manual intervention.

## Context
When LLM tasks fail, they often fail due to:
- Context too long for the model
- Token limits exceeded
- Model confusion from excessive context

We need automatic context simplification on retry that:
- Reduces context size progressively (100% → 70% → 40%)
- Maintains task integrity
- Improves success rates significantly

## Technical Requirements

### 1. Context Simplification Strategy
```python
def simplify_context(context: dict, reduction: float) -> dict:
    """
    Simplify context based on reduction factor:
    - 1.0 (100%): Full context (initial attempt)
    - 0.7 (70%): Remove low-priority info, summarize
    - 0.4 (40%): Keep only essential information
    
    Returns simplified context dict
    """
```

**Simplification Techniques:**
- **Summarization**: Replace long context with summaries
- **Pruning**: Remove low-priority information
- **Compression**: Remove whitespace, normalize formatting
- **Selection**: Keep only most relevant information

### 2. Progressive Reduction
```python
SIMPLIFICATION_STAGES = [1.0, 0.7, 0.4]  # Successive attempts
```

**Behavior:**
- Attempt 1: 100% context (full fidelity)
- Attempt 2: 70% context (summarize non-essential)
- Attempt 3: 40% context (keep only essentials)
- Stop after 3 attempts regardless of success

### 3. Context Types
Support simplification for different context types:
- **Task descriptions**: Summarize requirements
- **History/context**: Keep recent, summarize old
- **Tool outputs**: Summarize large outputs
- **Code snippets**: Keep structure, remove comments

### 4. Quality Preservation
- Never lose critical task information
- Preserve code structure and syntax
- Maintain tool output accuracy
- Track what was simplified for debugging

## Acceptance Criteria

### Functional Tests (All Must Pass)
1. ✅ Context reduces correctly at each stage (100% → 70% → 40%)
2. ✅ Critical information preserved across all stages
3. ✅ Code structure maintained after simplification
4. ✅ Tool outputs remain accurate
5. ✅ Simplification logs what was removed

### Integration Tests
1. ✅ Failed task automatically retries with simplified context
2. ✅ Success rate improvement measurable (target: +15%)
3. ✅ Cost savings from faster completions
4. ✅ No corruption of task data

### Performance
1. ✅ Simplification completes in <100ms
2. ✅ No performance impact on initial attempt
3. ✅ Minimal overhead on retry scenarios

### Documentation
1. ✅ README section: "Context Simplification"
2. ✅ Examples showing before/after simplification
3. ✅ Tuning guide for reduction factors
4. ✅ Troubleshooting for edge cases

## Implementation Tasks

### Week 15 (Day 1)
- [ ] Design context simplification API
- [ ] Implement 100% → 70% simplification
- [ ] Implement 70% → 40% simplification
- [ ] Unit tests for simplification logic

### Week 15 (Day 2)
- [ ] Integrate with retry logic
- [ ] Add automatic triggering on failure
- [ ] End-to-end testing with failed tasks
- [ ] Performance benchmarking

## Dependencies
- Context simplification algorithm (can start simple)
- Retry logic from Phase 1 (already exists)
- Token counting from cost tracker (already exists)

## Risks & Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| Over-simplification loses info | Medium | Start conservative, tune based on feedback |
| No improvement in success rates | Low | Monitor metrics, adjust reduction factors |
| Performance overhead | Low | Keep simplification fast (<100ms) |

## Success Metrics
- ✅ 15%+ improvement in task success rate on retries
- ✅ Average cost savings of 20% per failed task
- ✅ User satisfaction >4/5 on simplification quality
- ✅ Zero reports of corrupted task data

## Notes
- This feature directly improves reliability and reduces costs
- Must balance simplification with information preservation
- Start with simple summarization, iterate based on feedback
- Key differentiator: automatic, transparent simplification
