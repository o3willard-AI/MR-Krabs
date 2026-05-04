# Story P2-3: Context Simplification on Retry

**Priority**: P1 (High - Improves Success Rates)  
**Estimate**: 1 week  
**Phase**: Week 13

---

## User Story

As a developer  
I want automatic context simplification when tasks fail  
So that complex prompts can be retried with less context to improve success rates without manual intervention

---

## Acceptance Criteria

### AC1: Context Reduction Strategy

- [ ] First retry: Reduce context to 70% of original
- [ ] Second retry: Reduce context to 40% of original
- [ ] Third retry: Reduce context to 20% of original
- [ ] Reduction preserves task semantics
- [ ] Reduction logged for transparency

### AC2: Smart Context Selection

- [ ] Removes non-essential context first
- [ ] Preserves critical task requirements
- [ ] Removes duplicate information
- [ ] Compresses verbose explanations
- [ ] Keeps structured data intact

### AC3: Integration with Retry Logic

- [ ] Context simplification triggers on task failure
- [ ] Works with existing retry count (max 3 retries)
- [ ] Context level tracked per attempt
- [ ] Escalation continues after context reduction
- [ ] No manual intervention needed

### AC4: Context Reduction Methods

- [ ] Method 1: Remove peripheral information
- [ ] Method 2: Compress verbose sections
- [ ] Method 3: Remove redundant examples
- [ ] Method 4: Simplify structured data
- [ ] Method 5: Keep only essential instructions

### AC5: Task Integrity Preservation

- [ ] Core task requirements always preserved
- [ ] Input data integrity maintained
- [ ] Output format requirements kept
- [ ] Constraints and rules preserved
- [ ] Validation rules maintained

### AC6: Logging & Transparency

- [ ] Original context size logged
- [ ] Reduced context size logged
- [ ] Reduction method logged
- [ ] Success rate improvement tracked
- [ ] Debug mode shows context diffs

---

## Technical Implementation

### Files to Create/Modify

1. `src/core/context_simplifier.py` - New file for context reduction
2. `src/core/orchestrator.py` - Integrate simplification with retry
3. `src/core/cost.py` - Track context reduction attempts
4. `docs/user_stories/P2-3_CONTEXT_SIMPLIFICATION.md` - This story

### Implementation Plan

```python
# src/core/context_simplifier.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class ContextReductionResult:
    """Result of context simplification."""
    reduced_context: str
    original_size: int
    reduced_size: int
    reduction_percent: float
    method_used: str
    key_points_preserved: list[str]

class ContextSimplifier:
    """Smart context reduction for retry attempts."""
    
    REDUCTION_LEVELS = {
        1: 0.70,  # 70% of original
        2: 0.40,  # 40% of original
        3: 0.20,  # 20% of original
    }
    
    def __init__(self):
        self.preserved_patterns = [
            r"required output format:\s*.*",
            r"constraints:\s*.*",
            r"must\s+(include|use|follow|avoid)",
            r"input\s+(data|parameters):",
        ]
    
    def simplify_context(
        self, 
        original_context: str, 
        attempt: int,
        preserve_critical: bool = True
    ) -> ContextReductionResult:
        """
        Simplify context based on attempt number.
        
        Args:
            original_context: Full context from original task
            attempt: Current retry attempt (1, 2, or 3)
            preserve_critical: Whether to preserve critical patterns
        
        Returns:
            ContextReductionResult with simplified context and metadata
        """
        if attempt == 0:
            # No reduction on first attempt
            return ContextReductionResult(
                reduced_context=original_context,
                original_size=len(original_context),
                reduced_size=len(original_context),
                reduction_percent=0.0,
                method_used="none",
                key_points_preserved=[]
            )
        
        target_percent = self.REDUCTION_LEVELS.get(attempt, 0.20)
        target_size = int(len(original_context) * target_percent)
        
        # Extract critical points
        critical_points = []
        if preserve_critical:
            critical_points = self._extract_critical_points(original_context)
        
        # Apply reduction
        reduced = self._apply_reduction(
            original_context, 
            target_size,
            critical_points
        )
        
        return ContextReductionResult(
            reduced_context=reduced,
            original_size=len(original_context),
            reduced_size=len(reduced),
            reduction_percent=((len(original_context) - len(reduced)) / 
                             len(original_context) * 100),
            method_used=self._get_reduction_method(original_context, reduced),
            key_points_preserved=critical_points
        )
    
    def _extract_critical_points(self, context: str) -> list[str]:
        """Extract critical requirements from context."""
        critical_points = []
        
        for pattern in self.preserved_patterns:
            import re
            matches = re.findall(pattern, context, re.IGNORECASE | re.DOTALL)
            critical_points.extend(matches)
        
        # Also extract instructions, constraints, and output requirements
        instructions = self._extract_section(context, "instructions")
        constraints = self._extract_section(context, "constraints")
        requirements = self._extract_section(context, "requirements")
        
        critical_points.extend(instructions)
        critical_points.extend(constraints)
        critical_points.extend(requirements)
        
        return list(set(critical_points))  # Remove duplicates
    
    def _extract_section(self, context: str, section_name: str) -> list[str]:
        """Extract a section from context."""
        import re
        pattern = rf"{section_name}[:\s]+(.*?)(?=\n\n|\Z)"
        match = re.search(pattern, context, re.IGNORECASE | re.DOTALL)
        if match:
            return [match.group(1).strip()]
        return []
    
    def _apply_reduction(
        self, 
        context: str, 
        target_size: int,
        critical_points: list[str]
    ) -> str:
        """Apply context reduction strategy."""
        if len(context) <= target_size:
            return context
        
        # Strategy 1: Remove verbose explanations
        reduced = self._remove_verbose_explanations(context)
        
        # Strategy 2: Remove redundant examples
        if len(reduced) > target_size:
            reduced = self._remove_redundant_examples(reduced)
        
        # Strategy 3: Compress whitespace and formatting
        if len(reduced) > target_size:
            reduced = self._compress_whitespace(reduced)
        
        # Strategy 4: Remove duplicate content
        if len(reduced) > target_size:
            reduced = self._remove_duplicates(reduced)
        
        # Ensure critical points preserved
        reduced = self._ensure_critical_preserved(reduced, critical_points)
        
        return reduced
    
    def _remove_verbose_explanations(self, context: str) -> str:
        """Remove verbose explanations while keeping core content."""
        import re
        
        # Remove conversational fillers
        context = re.sub(
            r"\b(?:please|kindly|could you|would you|thank you)\b",
            "",
            context,
            flags=re.IGNORECASE
        )
        
        # Remove unnecessary hedging
        context = re.sub(
            r"\b(?:I think|possibly|perhaps|maybe|in my opinion)\b",
            "",
            context,
            flags=re.IGNORECASE
        )
        
        return context
    
    def _remove_redundant_examples(self, context: str) -> str:
        """Remove redundant or verbose examples."""
        import re
        
        # Identify and keep only essential examples
        # This is a simplified approach - real implementation would be smarter
        example_sections = re.findall(
            r"examples?\s*[:\n]+(.*?)(?=\n\n|\Z)",
            context,
            re.IGNORECASE | re.DOTALL
        )
        
        if len(example_sections) > 1:
            # Keep first example, remove rest
            context = re.sub(
                r"examples?\s*[:\n]+(.*?)(?=\n\n|\Z)",
                lambda m: example_sections[0] if example_sections.index(m.group(0)) > 0 else m.group(0),
                context,
                flags=re.IGNORECASE | re.DOTALL
            )
        
        return context
    
    def _compress_whitespace(self, context: str) -> str:
        """Compress whitespace and formatting."""
        import re
        
        # Remove multiple empty lines
        context = re.sub(r'\n\s*\n\s*\n+', '\n\n', context)
        
        # Remove extra spaces
        context = re.sub(r'  +', ' ', context)
        
        return context
    
    def _remove_duplicates(self, context: str) -> str:
        """Remove duplicate content."""
        import re
        
        # Simple duplicate line detection
        lines = context.split('\n')
        seen = set()
        unique_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and line_stripped not in seen:
                seen.add(line_stripped)
                unique_lines.append(line)
        
        return '\n'.join(unique_lines)
    
    def _ensure_critical_preserved(
        self, 
        context: str,
        critical_points: list[str]
    ) -> str:
        """Ensure critical points are preserved in reduced context."""
        for point in critical_points:
            if point not in context:
                # Add back the critical point at the beginning
                context = f"# CRITICAL: {point}\n{context}"
        
        return context
    
    def _get_reduction_method(
        self, 
        original: str, 
        reduced: str
    ) -> str:
        """Identify which reduction methods were applied."""
        if original == reduced:
            return "none"
        
        methods = []
        
        if len(original) - len(reduced) > len(original) * 0.3:
            methods.append("significant_reduction")
        else:
            methods.append("moderate_reduction")
        
        if "verbose" in original.lower() and "verbose" not in reduced.lower():
            methods.append("removed_verbose_content")
        
        return "; ".join(methods) if methods else "standard_reduction"
```

### Integration with Orchestrator

```python
# src/core/orchestrator.py

from src.core.context_simplifier import ContextSimplifier

class LLMOrchestrator:
    def __init__(self, project_root: str):
        self.context_simplifier = ContextSimplifier()
        # ... existing code ...
    
    def execute_task(
        self, 
        task_id: str, 
        tier: str, 
        context: dict, 
        max_attempts: int = 3
    ) -> dict:
        """Execute task with context simplification on retry."""
        original_context = context.get("task_description", "")
        
        for attempt in range(max_attempts):
            # Apply context simplification for retries
            if attempt > 0:
                result = self.context_simplifier.simplify_context(
                    original_context, 
                    attempt=attempt
                )
                
                # Log reduction
                print(f"[Retry {attempt}] "
                      f"Reduced context: {result.original_size} → "
                      f"{result.reduced_size} ({result.reduction_percent:.1f}%)")
                print(f"[Retry {attempt}] Method: {result.method_used}")
                
                # Use reduced context for this attempt
                context["task_description"] = result.reduced_context
            
            # Execute with current context
            result = self._execute_with_tier(task_id, tier, context)
            
            if result["success"]:
                return result
            
            # Release budget reservation on failure
            if attempt < max_attempts - 1:
                print(f"[Retry {attempt + 1}] Attempt failed, retrying with "
                      f"simplified context...")
        
        return {"success": False, "error": "All attempts failed"}
```

---

## Testing Requirements

### Unit Tests (test_context_simplifier.py)

1. `test_simplify_attempt_1_70_percent` - First retry: 70% reduction
2. `test_simplify_attempt_2_40_percent` - Second retry: 40% reduction
3. `test_simplify_attempt_3_20_percent` - Third retry: 20% reduction
4. `test_extract_critical_points` - Critical points preserved
5. `test_remove_verbose_explanations` - Verbose content removed
6. `test_remove_redundant_examples` - Examples compressed
7. `test_compress_whitespace` - Whitespace compressed
8. `test_remove_duplicates` - Duplicates removed
9. `test_preserve_critical_on_reduction` - Critical points always kept
10. `test_no_reduction_on_first_attempt` - First attempt unchanged

### Integration Tests

1. Task fails at L0, retry with 70% context → success
2. Task fails twice, final retry with 40% context → success
3. Context simplification improves success rate by 15%+
4. Critical requirements always met after simplification

---

## Out of Scope

- AI-powered context understanding (requires ML)
- Human-in-the-loop simplification
- Context expansion (only reduction)
- Custom simplification rules per task type

---

## Dependencies

- P1-5 complete (budget warnings, retry infrastructure)
- Core orchestrator working

---

## Performance Targets

| Metric | Target |
|--------|--------|
| **Simplification Speed** | <100ms |
| **Success Rate Improvement** | +15% |
| **Context Integrity** | 100% critical preserved |
| **Overhead** | <50ms per retry |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration tests pass
- [ ] Success rate improvement verified (>15%)
- [ ] Documentation updated
- [ ] Example included showing context reduction
- [ ] No breaking changes to existing code

---

## Success Metrics

- **Success Rate**: 15%+ improvement on retry tasks
- **Cost Savings**: 20% reduction in wasted attempts
- **User Satisfaction**: Positive feedback on reliability
- **Adoption**: Used in 50%+ of failing tasks

---

*Draft: April 26, 2026*
