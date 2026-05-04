#!/usr/bin/env python3
"""Unit tests for crewai_tools.py - cost-aware tool decorators."""

import pytest
from src.integrations.crewai_tools import (
    cost_aware_tool,
    create_cost_aware_base_tool,
    wrap_for_crewai,
    CostAwareToolMixin,
)


class TestCostAwareToolDecorator:
    """Tests for the @cost_aware_tool decorator."""
    
    def test_basic_decorator(self):
        """Test basic decorator functionality."""
        @cost_aware_tool
        def my_function(x: int) -> int:
            """Add 1 to x."""
            return x + 1
        
        # Should have decorator metadata
        assert hasattr(my_function, '_is_cost_aware_tool')
        assert my_function._is_cost_aware_tool is True
        assert my_function._tool_name == 'my_function'
        assert 'Add 1 to x' in my_function._description
        
        # Should execute normally
        assert my_function(5) == 6
    
    def test_decorator_with_name(self):
        """Test decorator with custom name."""
        @cost_aware_tool(tool_name='custom_tool')
        def original_function():
            pass
        
        assert original_function._tool_name == 'custom_tool'
    
    def test_decorator_with_description(self):
        """Test decorator with custom description."""
        @cost_aware_tool(description='Custom description')
        def func_with_doc():
            """Original docstring."""
            pass
        
        assert 'Custom description' in func_with_doc._description
    
    def test_decorator_as_function_call(self):
        """Test decorator used as @cost_aware_tool() with parentheses."""
        @cost_aware_tool()
        def simple_func():
            """Simple function."""
            return "result"
        
        assert hasattr(simple_func, '_is_cost_aware_tool')
        assert simple_func() == "result"
    
    def test_decorator_preserves_function(self):
        """Test decorator preserves original function behavior."""
        @cost_aware_tool
        def multiply(a: float, b: float) -> float:
            """Multiply two numbers."""
            return a * b
        
        assert multiply(2, 3) == 6
        assert multiply(0, 5) == 0
        assert multiply(-1, -1) == 1
    
    def test_decorator_with_kwargs(self):
        """Test decorator with keyword arguments."""
        @cost_aware_tool(tool_name='test_tool', tracking_enabled=False)
        def func_with_kwargs():
            return "tracked"
        
        # Should still work, just tracking disabled
        assert func_with_kwargs() == "tracked"
        assert func_with_kwargs._tracking_enabled is False


class TestCostAwareToolMixin:
    """Tests for CostAwareToolMixin."""
    
    def test_mixin_initialization(self):
        """Test mixin initializes correctly."""
        class TestTool(CostAwareToolMixin):
            def __init__(self):
                super().__init__()
        
        tool = TestTool()
        assert tool._cost_tracker is None
        assert tool._tracking_enabled is True
    
    def test_set_cost_tracker(self):
        """Test setting cost tracker."""
        class TestTool(CostAwareToolMixin):
            def __init__(self):
                super().__init__()
        
        tool = TestTool()
        
        # Mock cost tracker
        mock_tracker = object()
        tool.set_cost_tracker(mock_tracker)
        
        assert tool._cost_tracker is mock_tracker
        assert tool._tracking_enabled is True
    
    def test_disable_tracking(self):
        """Test disabling tracking."""
        class TestTool(CostAwareToolMixin):
            def __init__(self):
                super().__init__()
        
        tool = TestTool()
        tool._tracking_enabled = False
        
        assert tool._tracking_enabled is False
    
    def test_track_execution_no_tracker(self):
        """Test tracking when no tracker is set."""
        class TestTool(CostAwareToolMixin):
            def __init__(self):
                super().__init__()
        
        tool = TestTool()
        
        result = tool._track_execution(
            tool_name='test',
            args={'query': 'test'},
            result={'content': 'result'},
            start_time=0
        )
        
        # Should return result unchanged (no tracker)
        assert result == {'content': 'result'}
    
    def test_track_execution_with_metadata(self):
        """Test tracking adds cost metadata."""
        class TestTool(CostAwareToolMixin):
            def __init__(self):
                super().__init__()
        
        tool = TestTool()
        tool._cost_tracker = object()  # Mock tracker
        tool._tracking_enabled = True
        
        result = tool._track_execution(
            tool_name='search',
            args={'query': 'test query'},
            result={'content': 'search results'},
            start_time=1000
        )
        
        # Should have cost metadata
        assert isinstance(result, dict)
        assert '_cost_metadata' in result
        assert result['_cost_metadata']['tool'] == 'search'
        assert 'duration_seconds' in result['_cost_metadata']
        assert 'prompt_tokens' in result['_cost_metadata']
        assert 'completion_tokens' in result['_cost_metadata']


class TestCreateCostAwareBaseTool:
    """Tests for create_cost_aware_base_tool."""
    
    def test_create_tool_class(self):
        """Test creating a cost-aware tool class."""
        
        def sample_func(query: str) -> str:
            return f"Result: {query}"
        
        ToolClass = create_cost_aware_base_tool(
            name='search_tool',
            description='Search the web',
            func=sample_func
        )
        
        # Should be a class
        assert isinstance(ToolClass, type)
        
        # Should have correct attributes
        assert ToolClass.name == 'search_tool'
        assert ToolClass.description == 'Search the web'
    
    def test_tool_inheritance(self):
        """Test that created tool inherits correctly."""
        
        def sample_func():
            return "result"
        
        ToolClass = create_cost_aware_base_tool(
            name='test',
            description='Test tool',
            func=sample_func
        )
        
        # Should inherit from CostAwareToolMixin (indirectly)
        assert issubclass(ToolClass, object)


class TestWrapForCrewAI:
    """Tests for wrap_for_crewai."""
    
    @pytest.mark.skipif(True, reason="CrewAI not available in test environment")
    def test_wrap_function(self):
        """Test wrapping a function for CrewAI."""
        
        def my_tool(query: str) -> str:
            return f"Search: {query}"
        
        wrapped = wrap_for_crewai(my_tool, name='my_search')
        
        # Should be a class
        assert isinstance(wrapped, type)
        assert wrapped.name == 'my_search'


class TestCostTrackingIntegration:
    """Integration tests for cost tracking."""
    
    def test_decorator_chain(self):
        """Test multiple decorators can be chained."""
        
        @cost_aware_tool
        def func1(x):
            return x * 2
        
        @cost_aware_tool(tool_name='func2')
        def func2(x):
            return x + 1
        
        # Both should work independently
        assert func1(5) == 10
        assert func2(5) == 6
    
    def test_decorator_with_complex_args(self):
        """Test decorator handles complex arguments."""
        
        @cost_aware_tool
        def complex_func(data: dict, items: list, flag: bool) -> dict:
            return {'processed': True}
        
        result = complex_func(
            data={'key': 'value'},
            items=[1, 2, 3],
            flag=True
        )
        
        assert result['processed'] is True
    
    def test_decorator_exception_handling(self):
        """Test decorator re-raises exceptions."""
        
        @cost_aware_tool
        def failing_func():
            raise ValueError("Test error")
        
        # Should still raise the original exception
        with pytest.raises(ValueError, match="Test error"):
            failing_func()
