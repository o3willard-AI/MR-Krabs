#!/usr/bin/env python3
"""Simple test script for TracingAdapter functionality."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.metrics.tracing import TracingAdapter, Span

def test_span_creation():
    """Test basic span creation."""
    print("Testing span creation...")
    span = Span(name="test.operation")
    assert span.name == "test.operation"
    assert len(span.span_id) == 16
    assert len(span.trace_id) == 32
    print("✓ Span creation works")

def test_span_duration():
    """Test span duration calculation."""
    print("Testing span duration...")
    span = Span(name="test")
    span.finish()
    assert span.duration_ms >= 0
    print("✓ Span duration works")

def test_span_events():
    """Test span events."""
    print("Testing span events...")
    span = Span(name="test")
    span.add_event("cache.miss", key="abc")
    span.add_event("provider.call", model="gpt-4o")
    assert len(span.events) == 2
    print("✓ Span events work")

def test_span_to_dict():
    """Test converting span to dictionary."""
    print("Testing span to_dict...")
    span = Span(name="test")
    span.set_attribute("task_id", "abc123")
    span.finish()
    d = span.to_dict()
    assert d["name"] == "test"
    assert d["attributes"]["task_id"] == "abc123"
    print("✓ Span to_dict works")

def test_tracing_adapter():
    """Test tracing adapter functionality."""
    print("Testing tracing adapter...")
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    # Test disabled by default
    config_disabled = {"test": "value"}
    tracer_disabled = TracingAdapter(config=config_disabled)
    assert tracer_disabled.enabled is False
    
    # Test enabled with config
    assert tracer.enabled is True
    
    # Test start and finish span
    span = tracer.start_span("ask", task_id="task-1")
    tracer.finish_span(span)
    traces = tracer.get_traces()
    assert len(traces) == 1
    assert traces[0]["name"] == "ask"
    
    print("✓ Tracing adapter works")

def test_parent_child_spans():
    """Test parent/child span relationships."""
    print("Testing parent/child spans...")
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    parent = tracer.start_span("ask", task_id="task-2")
    child = tracer.start_span("route.select", parent=parent)
    assert child.trace_id == parent.trace_id
    assert child.parent_id == parent.span_id
    tracer.finish_span(child)
    tracer.finish_span(parent)
    assert len(tracer.get_traces()) == 2
    
    print("✓ Parent/child spans work")

def test_context_manager():
    """Test context manager."""
    print("Testing context manager...")
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    with tracer.trace("provider.call", model="gpt-4o") as span:
        span.add_event("request.sent")
    
    traces = tracer.get_traces()
    assert len(traces) == 1
    print("✓ Context manager works")

def test_error_handling():
    """Test error handling in context manager."""
    print("Testing error handling...")
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    try:
        with tracer.trace("risky.operation"):
            raise ValueError("test error")
    except ValueError:
        pass
    
    traces = tracer.get_traces()
    assert traces[0]["status"] == "error"
    print("✓ Error handling works")

if __name__ == "__main__":
    print("Running TracingAdapter tests...")
    
    test_span_creation()
    test_span_duration()
    test_span_events()
    test_span_to_dict()
    test_tracing_adapter()
    test_parent_child_spans()
    test_context_manager()
    test_error_handling()
    
    print("\n✅ All tests passed!")