"""OpenTelemetry-compatible distributed tracing adapter.

Provides span-based tracing across all MR-Krabs operations.
Uses lightweight span abstraction — swap in real OTel SDK for production.
"""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..adapters.base_adapter import LiteLLMAdapter, HealthStatus


@dataclass
class SpanEvent:
    """An event within a span."""
    name: str
    timestamp: float = field(default_factory=time.monotonic)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A trace span representing a unit of work."""
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.monotonic)
    end_time: Optional[float] = None
    status: str = "ok"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0
    
    def add_event(self, name: str, **attributes):
        self.events.append(SpanEvent(name=name, attributes=attributes))
    
    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value
    
    def finish(self, status: str = "ok"):
        self.end_time = time.monotonic()
        self.status = status
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": [{"name": e.name, "attrs": e.attributes} for e in self.events],
        }


class TracingAdapter(LiteLLMAdapter):
    """Distributed tracing adapter for MR-Krabs.
    
    Creates spans for: ask(), routing, provider calls, tier escalation, vault ops.
    Uses in-memory span storage (console export for debugging).
    Swap in opentelemetry-sdk for production OTLP export.
    """
    
    def __init__(self, config=None, name="tracing"):
        super().__init__(config or {}, name)
        self._spans: Dict[str, Span] = {}
        self._finished_spans: List[Span] = []
        self._max_finished = 1000
    
    @property
    def enabled(self) -> bool:
        return self.get_config("enable_tracing", default=False)
    
    def initialize(self) -> bool:
        self._initialized = True
        return True
    
    def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY
    
    def shutdown(self) -> None:
        self._initialized = False
    
    def start_span(self, name: str, parent: Optional[Span] = None, **attributes) -> Span:
        """Start a new span. If disabled, returns a no-op span."""
        if not self.enabled:
            return Span(name="noop")
        
        span = Span(
            name=name,
            trace_id=parent.trace_id if parent else uuid.uuid4().hex[:32],
            parent_id=parent.span_id if parent else None,
        )
        for k, v in attributes.items():
            span.set_attribute(k, v)
        
        self._spans[span.span_id] = span
        return span
    
    def finish_span(self, span: Span, status: str = "ok"):
        """Finish a span and archive it."""
        if span.name == "noop":
            return
        span.finish(status)
        self._spans.pop(span.span_id, None)
        self._finished_spans.append(span)
        if len(self._finished_spans) > self._max_finished:
            self._finished_spans.pop(0)
    
    @contextmanager
    def trace(self, name: str, parent: Optional[Span] = None, **attributes):
        """Context manager for tracing a block of code."""
        span = self.start_span(name, parent, **attributes)
        try:
            yield span
            self.finish_span(span, "ok")
        except Exception as e:
            span.add_event("error", message=str(e))
            self.finish_span(span, "error")
            raise
    
    def get_traces(self, limit: int = 50) -> List[dict]:
        """Return recent trace data for analytics."""
        return [s.to_dict() for s in self._finished_spans[-limit:]]
    
    def get_trace_by_id(self, trace_id: str) -> List[dict]:
        """Get all spans for a trace."""
        return [s.to_dict() for s in self._finished_spans if s.trace_id == trace_id]