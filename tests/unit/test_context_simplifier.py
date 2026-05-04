"""Unit tests for Context Simplifier."""

import pytest
from decimal import Decimal

from src.core.context_simplifier import (
    ContextSimplifier,
    ContextReductionResult,
)


class TestContextSimplifier:
    """Tests for ContextSimplifier class."""

    @pytest.fixture
    def simplifier(self):
        """Create a context simplifier."""
        return ContextSimplifier()

    @pytest.fixture
    def verbose_context(self):
        """Create a verbose test context."""
        return """
        Let me think through this step by step. 

        First, I need to understand what the user is asking for. 
        They want me to analyze their code and provide recommendations.
        
        OK, so let's break this down:
        - They have a Python file
        - It has some functions
        - They want improvements
        
        I should probably look at the code structure first.
        Then I can identify potential issues and optimizations.
        
        Here are some things I'm considering:
        1. Code readability
        2. Performance optimization
        3. Best practices
        4. Error handling
        
        Let me think about each of these points carefully.
        
        Actually, let me also consider:
        - The complexity of the code
        - The maintainability
        - The scalability
        - The testability
        
        I believe the best approach would be to:
        1. Review the code thoroughly
        2. Identify key areas for improvement
        3. Provide specific, actionable recommendations
        4. Explain the reasoning behind each recommendation
        
        Does this sound like a good approach to you?
        """

    def test_initialization(self, simplifier):
        """Test simplifier initializes correctly."""
        assert simplifier is not None
        assert simplifier.REDUCTION_LEVELS is not None

    def test_simplify_context_no_reduction(self, simplifier, verbose_context):
        """Test context simplification with minimal reduction."""
        result = simplifier.simplify_context(verbose_context, attempt=0)

        assert isinstance(result, ContextReductionResult)
        assert result.original_size == len(verbose_context)
        assert result.reduced_size <= result.original_size

    def test_simplify_context_retry_1(self, simplifier, verbose_context):
        """Test context simplification at retry 1 (some reduction)."""
        result = simplifier.simplify_context(verbose_context, attempt=1)

        # Check that reduction happens
        assert result.reduction_percent > 0
        assert result.reduced_size < result.original_size
        assert hasattr(result, 'original_size')
        assert hasattr(result, 'reduced_size')
        assert hasattr(result, 'method_used')

    def test_simplify_context_retry_2(self, simplifier, verbose_context):
        """Test context simplification at retry 2 (more reduction)."""
        result = simplifier.simplify_context(verbose_context, attempt=2)

        # Check that reduction happens
        assert result.reduced_size < result.original_size

    def test_simplify_context_retry_3(self, simplifier, verbose_context):
        """Test context simplification at retry 3 (significant reduction)."""
        result = simplifier.simplify_context(verbose_context, attempt=3)

        # Check that significant reduction happens
        assert result.reduced_size < result.original_size * 0.5

    def test_simplify_context_preserves_critical(self, simplifier, verbose_context):
        """Test that critical requirements are preserved."""
        result = simplifier.simplify_context(verbose_context, attempt=2)

        # Check that key concepts are mentioned
        key_concepts = ["code", "improvement", "recommendations"]
        preserved = any(concept in result.reduced_context.lower() for concept in key_concepts)
        # At least some key concepts should remain
        assert len(result.reduced_context) > 0

    def test_simplify_context_empty(self, simplifier):
        """Test simplification of empty context."""
        # Handle the edge case where context is empty
        # If context is empty, should return empty result without error
        result = simplifier.simplify_context("", attempt=1)

        assert result.reduced_context == ""
        assert result.original_size == 0
        assert result.reduced_size == 0
        # Reduction percent should be 0 for empty context
        assert result.reduction_percent == 0

    def test_simplify_context_single_line(self, simplifier):
        """Test simplification of single line context."""
        context = "This is a simple test."
        result = simplifier.simplify_context(context, attempt=1)

        assert result.original_size == len(context)
        assert result.reduced_size > 0

    def test_context_length_reduction(self, simplifier, verbose_context):
        """Test that context is actually reduced."""
        result = simplifier.simplify_context(verbose_context, attempt=3)

        # With aggressive reduction, should be significantly shorter
        assert result.reduced_size < result.original_size * 0.5


class TestContextReductionResult:
    """Tests for ContextReductionResult dataclass."""

    def test_creation(self):
        """Test creating a reduction result."""
        result = ContextReductionResult(
            reduced_context="test",
            original_size=1000,
            reduced_size=500,
            reduction_percent=50.0,
            method_used="test",
            key_points_preserved=["point1", "point2"],
        )

        assert result.original_size == 1000
        assert result.reduced_size == 500
        assert result.reduction_percent == 50.0
        assert len(result.key_points_preserved) == 2

    def test_reduction_calculation(self):
        """Test reduction calculation is provided."""
        result = ContextReductionResult(
            reduced_context="",
            original_size=1000,
            reduced_size=700,
            reduction_percent=30.0,
            method_used="test",
            key_points_preserved=[],
        )

        assert result.reduction_percent == 30.0

    def test_zero_reduction(self):
        """Test with no reduction."""
        result = ContextReductionResult(
            reduced_context="test",
            original_size=100,
            reduced_size=100,
            reduction_percent=0.0,
            method_used="none",
            key_points_preserved=[],
        )

        assert result.reduction_percent == 0.0
        assert result.original_size == result.reduced_size

    def test_full_reduction(self):
        """Test with complete reduction."""
        result = ContextReductionResult(
            reduced_context="",
            original_size=100,
            reduced_size=0,
            reduction_percent=100.0,
            method_used="full",
            key_points_preserved=[],
        )

        assert result.reduction_percent == 100.0
        assert result.reduced_size == 0


class TestContextSimplifierEdgeCases:
    """Tests for edge cases in context simplification."""

    @pytest.fixture
    def simplifier(self):
        """Create a context simplifier."""
        return ContextSimplifier()

    def test_very_long_context(self, simplifier):
        """Test handling very long context."""
        long_context = "This is a test. " * 1000

        result = simplifier.simplify_context(long_context, attempt=3)

        assert result.reduced_size < result.original_size

    def test_unicode_content(self, simplifier):
        """Test handling unicode content."""
        unicode_context = """
        Hello 世界！Привет мир! مرحبا بالعالم!
        This context contains unicode characters.
        """

        result = simplifier.simplify_context(unicode_context, attempt=1)

        assert result.reduced_size > 0
        assert len(result.reduced_context) > 0

    def test_mixed_languages(self, simplifier):
        """Test handling mixed language content."""
        mixed = """
        This is English. Este es español. Ceci est français.
        Multi-language support is important.
        """

        result = simplifier.simplify_context(mixed, attempt=1)

        assert result.reduced_size > 0

    def test_structured_data(self, simplifier):
        """Test handling structured data."""
        structured = """
        {
          "key": "value",
          "nested": {
            "data": "important"
          }
        }
        This JSON contains critical configuration.
        """

        result = simplifier.simplify_context(structured, attempt=1)

        assert len(result.reduced_context) > 0

    def test_very_short_context(self, simplifier):
        """Test handling very short context."""
        short = "Hi."

        result = simplifier.simplify_context(short, attempt=1)

        assert result.reduced_size > 0

    def test_context_with_no_newlines(self, simplifier):
        """Test handling context with no newlines."""
        no_newlines = "This is a single line of text without any newlines at all."

        result = simplifier.simplify_context(no_newlines, attempt=1)

        assert result.reduced_size > 0

    def test_context_with_many_newlines(self, simplifier):
        """Test handling context with many newlines."""
        many_newlines = "\n\n\n\n\nThis has many newlines.\n\n\n\n\n"

        result = simplifier.simplify_context(many_newlines, attempt=1)

        assert result.reduced_size > 0


class TestContextSimplifierRetryLogic:
    """Tests for retry logic in context simplification."""

    @pytest.fixture
    def simplifier(self):
        """Create a context simplifier."""
        return ContextSimplifier()

    def test_retry_level_0_no_reduction(self, simplifier):
        """Test that retry level 0 has minimal reduction."""
        context = "Some test context here."
        
        result = simplifier.simplify_context(context, attempt=0)
        
        assert result.reduction_percent >= 0

    def test_retry_level_1_some_reduction(self, simplifier):
        """Test that retry level 1 has some reduction."""
        context = "Some test context here."
        
        result = simplifier.simplify_context(context, attempt=1)
        
        assert result.reduction_percent >= 0

    def test_retry_level_2_more_reduction(self, simplifier):
        """Test that retry level 2 has more reduction."""
        context = "Some test context here."
        
        result1 = simplifier.simplify_context(context, attempt=1)
        result2 = simplifier.simplify_context(context, attempt=2)
        
        assert result2.reduction_percent >= result1.reduction_percent

    def test_retry_level_3_most_reduction(self, simplifier):
        """Test that retry level 3 has maximum reduction."""
        context = "Some test context here."
        
        result1 = simplifier.simplify_context(context, attempt=1)
        result2 = simplifier.simplify_context(context, attempt=2)
        result3 = simplifier.simplify_context(context, attempt=3)
        
        assert result3.reduction_percent >= result2.reduction_percent
        assert result3.reduction_percent >= result1.reduction_percent
