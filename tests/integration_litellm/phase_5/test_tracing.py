"""Phase 5: Tracing adapter tests."""

import pytest
from src.metrics.tracing import TracingAdapter, Span


@pytest.fixture
def mock_config():
    return {
        "test": "value"
    }


@pytest.fixture
def tracer(mock_config):
    config = mock_config.copy()
    config["enable_tracing"] = True
    return TracingAdapter(config=config)


class TestSpan:
    def test_span_creation(self):
        span = Span(name="test.operation")
        assert span.name == "test.operation"
        assert len(span.span_id) == 16
        assert len(span.trace_id) == 32
    
    def test_span_duration(self):
        span = Span(name="test")
        span.finish()
        assert span.duration_ms >= 0
    
    def test_span_events(self):
        span = Span(name="test")
        span.add_event("cache.miss", key="abc")
        span.add_event("provider.call", model="gpt-4o")
        assert len(span.events) == 2
    
    def test_span_to_dict(self):
        span = Span(name="test")
        span.set_attribute("task_id", "abc123")
        span.finish()
        d = span.to_dict()
        assert d["name"] == "test"
        assert d["attributes"]["task_id"] == "abc123"


class TestTracingAdapter:
    def test_disabled_by_default(self, mock_config):
        t = TracingAdapter(config=mock_config)
        assert t.enabled is False
    
    def test_enabled_with_config(self, tracer):
        assert tracer.enabled is True
    
    def test_start_and_finish_span(self, tracer):
        span = tracer.start_span("ask", task_id="task-1")
        tracer.finish_span(span)
        traces = tracer.get_traces()
        assert len(traces) == 1
        assert traces[0]["name"] == "ask"
    
    def test_trace_context_manager(self, tracer):
        with tracer.trace("provider.call", model="gpt-4o") as span:
            span.add_event("request.sent")
        traces = tracer.get_traces()
        assert len(traces) == 1
    
    def test_trace_error_handling(self, tracer):
        try:
            with tracer.trace("risky.operation"):
                raise ValueError("test error")
        except ValueError:
            pass
        traces = tracer.get_traces()
        assert traces[0]["status"] == "error"
    
    def test_parent_child_spans(self, tracer):
        parent = tracer.start_span("ask", task_id="task-2")
        child = tracer.start_span("route.select", parent=parent)
        assert child.trace_id == parent.trace_id
        assert child.parent_id == parent.span_id
        tracer.finish_span(child)
        tracer.finish_span(parent)
        assert len(tracer.get_traces()) == 2
    
    def test_disabled_returns_noop(self, mock_config):
        t = TracingAdapter(config=mock_config)
        span = t.start_span("test")
        assert span.name == "noop"
    
    def test_get_trace_by_id(self, tracer):
        s1 = tracer.start_span("step1")
        trace_id = s1.trace_id
        tracer.finish_span(s1)
        
        s2 = tracer.start_span("step2")
        s2.trace_id = trace_id
        tracer.finish_span(s2)
        
        results = tracer.get_trace_by_id(trace_id)
        assert len(results) >= 1
    
    def test_max_finished_spans(self, tracer):
        for i in range(1100):
            span = tracer.start_span(f"span_{i}")
            tracer.finish_span(span)
        traces = tracer.get_traces(limit=2000)
        assert len(traces) <= 1000  # Capped
    
    def test_multiple_spans_same_trace(self, tracer):
        """Test that multiple spans can belong to the same trace."""
        span1 = tracer.start_span("span1")
        span2 = tracer.start_span("span2", parent=span1)
        span3 = tracer.start_span("span3", parent=span1)
        
        assert span1.trace_id == span2.trace_id
        assert span1.trace_id == span3.trace_id
        assert span2.parent_id == span1.span_id
        assert span3.parent_id == span1.span_id
        
        tracer.finish_span(span1)
        tracer.finish_span(span2)
        tracer.finish_span(span3)
        
        traces = tracer.get_traces()
        assert len(traces) == 3
    
    def test_nested_trace_context_manager(self, tracer):
        """Test nested context managers."""
        with tracer.trace("outer") as outer:
            with tracer.trace("inner", parent=outer) as inner:
                inner.add_event("nested.event")
        
        traces = tracer.get_traces()
        assert len(traces) == 2
        trace_names = [t["name"] for t in traces]
        assert "outer" in trace_names
        assert "inner" in trace_names
    
    def test_trace_with_attributes(self, tracer):
        """Test spans with various attributes."""
        with tracer.trace("attribute.test", task_id="task-456", model="gpt-4") as span:
            span.add_event("test.event", result="success")
        
        traces = tracer.get_traces()
        assert len(traces) == 1
        trace = traces[0]
        assert trace["attributes"]["task_id"] == "task-456"
        assert trace["attributes"]["model"] == "gpt-4"
        assert len(trace["events"]) == 1
        assert trace["events"][0]["name"] == "test.event"
    
    def test_trace_duration_calculation(self, tracer):
        """Test that span duration is calculated correctly."""
        import time
        
        with tracer.trace("duration.test") as span:
            time.sleep(0.01)  # Sleep for 10ms
            
        traces = tracer.get_traces()
        assert len(traces) == 1
        duration = traces[0]["duration_ms"]
        # Should be at least 10ms (allowing for some overhead)
        assert duration >= 5
    
    def test_span_attributes_and_events(self, tracer):
        """Test comprehensive span attribute and event handling."""
        with tracer.trace("comprehensive.test") as span:
            span.set_attribute("user_id", "user-123")
            span.set_attribute("session_id", "sess-456")
            span.add_event("start", timestamp=1000)
            span.add_event("processing", progress=50, status="in_progress")
            span.add_event("complete", success=True)
        
        traces = tracer.get_traces()
        assert len(traces) == 1
        trace = traces[0]
        
        # Check attributes
        assert trace["attributes"]["user_id"] == "user-123"
        assert trace["attributes"]["session_id"] == "sess-456"
        
        # Check events
        assert len(trace["events"]) == 3
        event_names = [e["name"] for e in trace["events"]]
        assert "start" in event_names
        assert "processing" in event_names
        assert "complete" in event_names
        
        # Check specific event attributes
        processing_event = next(e for e in trace["events"] if e["name"] == "processing")
        assert processing_event["attrs"]["progress"] == 50
        assert processing_event["attrs"]["status"] == "in_progress"


class TestNestedTracing:
    """Simulate real ask() flow."""
    
    def test_full_ask_flow(self, tracer):
        with tracer.trace("mrkrabs.ask", task_id="task-123") as root:
            with tracer.trace("mrkrabs.route.select", parent=root, strategy="smart") as route:
                route.add_event("candidates.evaluated", count=5)
            with tracer.trace("mrkrabs.provider.complete", parent=root, model="gpt-4o-mini") as prov:
                prov.add_event("request.sent")
                prov.add_event("response.received", tokens=150)
            with tracer.trace("mrkrabs.vault.read", parent=root, path="/providers/openai") as vault:
                vault.add_event("cache.hit")
        
        traces = tracer.get_traces()
        assert len(traces) == 4
        names = [t["name"] for t in traces]
        assert "mrkrabs.ask" in names
        assert "mrkrabs.route.select" in names