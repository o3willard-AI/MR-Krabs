"""Phase 5: Tracing adapter tests - simplified version."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../../../')

from src.metrics.tracing import TracingAdapter, Span

def test_span_creation():
    """Test basic span creation."""
    span = Span(name="test.operation")
    assert span.name == "test.operation"
    assert len(span.span_id) == 16
    assert len(span.trace_id) == 32

def test_span_duration():
    """Test span duration calculation."""
    span = Span(name="test")
    span.finish()
    assert span.duration_ms >= 0

def test_span_events():
    """Test span events."""
    span = Span(name="test")
    span.add_event("cache.miss", key="abc")
    span.add_event("provider.call", model="gpt-4o")
    assert len(span.events) == 2

def test_span_to_dict():
    """Test converting span to dictionary."""
    span = Span(name="test")
    span.set_attribute("task_id", "abc123")
    span.finish()
    d = span.to_dict()
    assert d["name"] == "test"
    assert d["attributes"]["task_id"] == "abc123"

def test_tracing_adapter_disabled_by_default():
    """Test tracing adapter disabled by default."""
    config = {"test": "value"}
    t = TracingAdapter(config=config)
    assert t.enabled is False

def test_tracing_adapter_enabled_with_config():
    """Test tracing adapter enabled with config."""
    config = {"enable_tracing": True}
    t = TracingAdapter(config=config)
    assert t.enabled is True

def test_start_and_finish_span():
    """Test start and finish span."""
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    span = tracer.start_span("ask", task_id="task-1")
    tracer.finish_span(span)
    traces = tracer.get_traces()
    assert len(traces) == 1
    assert traces[0]["name"] == "ask"

def test_parent_child_spans():
    """Test parent/child span relationships."""
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    parent = tracer.start_span("ask", task_id="task-2")
    child = tracer.start_span("route.select", parent=parent)
    assert child.trace_id == parent.trace_id
    assert child.parent_id == parent.span_id
    tracer.finish_span(child)
    tracer.finish_span(parent)
    assert len(tracer.get_traces()) == 2

def test_context_manager():
    """Test context manager."""
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    with tracer.trace("provider.call", model="gpt-4o") as span:
        span.add_event("request.sent")
    
    traces = tracer.get_traces()
    assert len(traces) == 1

def test_error_handling():
    """Test error handling in context manager."""
    config = {"enable_tracing": True}
    tracer = TracingAdapter(config=config)
    
    try:
        with tracer.trace("risky.operation"):
            raise ValueError("test error")
    except ValueError:
        pass
    
    traces = tracer.get_traces()
    assert traces[0]["status"] == "error"

def test_disabled_returns_noop():
    """Test disabled returns no-op span."""
    config = {"test": "value"}
    t = TracingAdapter(config=config)
    span = t.start_span("test")
    assert span.name == "noop"