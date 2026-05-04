"""
Error metrics tracking for cost-aware error handling.
Part of P4-3: Cost-Aware Error Handling.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import threading


@dataclass
class ErrorMetrics:
    """Aggregated error metrics for a task or system."""
    
    error_count: int = 0
    """Total number of errors encountered."""
    
    retry_count: int = 0
    """Total number of retry attempts made."""
    
    escalation_count: int = 0
    """Number of times error triggered tier escalation."""
    
    recovery_success_rate: float = 0.0
    """Percentage of errors successfully recovered (0.0 to 1.0)."""
    
    avg_recovery_time_seconds: float = 0.0
    """Average time to recover from error (seconds)."""
    
    error_type_breakdown: dict = field(default_factory=dict)
    """Count of errors by type (e.g., {'timeout': 5, 'network': 3})."""
    
    budget_impact: Decimal = field(default_factory=lambda: Decimal("0.00"))
    """Total cost impact from error recovery attempts."""
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary for serialization."""
        return {
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "escalation_count": self.escalation_count,
            "recovery_success_rate": round(self.recovery_success_rate, 3),
            "avg_recovery_time_seconds": round(self.avg_recovery_time_seconds, 2),
            "error_type_breakdown": dict(self.error_type_breakdown),
            "budget_impact": str(self.budget_impact),
        }


class ErrorMetricsCollector:
    """
    Collects and aggregates error metrics.
    
    Thread-safe for concurrent error recording.
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._lock = threading.Lock()
        self._error_count = 0
        self._retry_count = 0
        self._escalation_count = 0
        self._recovered_count = 0
        self._recovery_times: list[float] = []
        self._error_types: dict[str, int] = {}
        self._budget_impact = Decimal("0.00")
    
    def record_error(
        self,
        error_type: str,
        error_category: str,
        recovered: bool,
        recovery_time_seconds: Optional[float],
        cost_impact: Decimal,
        triggered_escalation: bool = False
    ) -> None:
        """
        Record an error occurrence.
        
        Args:
            error_type: Type of error (e.g., "timeout", "network")
            error_category: Classification category
            recovered: Whether error was successfully recovered
            recovery_time_seconds: Time taken to recover (if recovered)
            cost_impact: Cost impact of this error/recovery
            triggered_escalation: Whether this triggered tier escalation
        """
        with self._lock:
            self._error_count += 1
            
            # Track error type
            self._error_types[error_type] = self._error_types.get(error_type, 0) + 1
            
            # Track recovery
            if recovered:
                self._recovered_count += 1
                if recovery_time_seconds is not None:
                    self._recovery_times.append(recovery_time_seconds)
            
            # Track escalation
            if triggered_escalation:
                self._escalation_count += 1
            
            # Track budget impact
            self._budget_impact += cost_impact
    
    def record_retry(self) -> None:
        """Record a retry attempt."""
        with self._lock:
            self._retry_count += 1
    
    def get_metrics(self) -> ErrorMetrics:
        """Get current error metrics."""
        with self._lock:
            # Calculate recovery success rate
            if self._error_count > 0:
                recovery_rate = self._recovered_count / self._error_count
            else:
                recovery_rate = 0.0
            
            # Calculate average recovery time
            if self._recovery_times:
                avg_recovery = sum(self._recovery_times) / len(self._recovery_times)
            else:
                avg_recovery = 0.0
            
            return ErrorMetrics(
                error_count=self._error_count,
                retry_count=self._retry_count,
                escalation_count=self._escalation_count,
                recovery_success_rate=round(recovery_rate, 3),
                avg_recovery_time_seconds=round(avg_recovery, 2),
                error_type_breakdown=dict(self._error_types),
                budget_impact=self._budget_impact
            )
    
    def get_summary(self) -> dict:
        """Get metrics summary as dictionary."""
        metrics = self.get_metrics()
        return {
            "total_errors": metrics.error_count,
            "total_retries": metrics.retry_count,
            "total_escalations": metrics.escalation_count,
            "recovery_success_rate": metrics.recovery_success_rate,
            "avg_recovery_time": metrics.avg_recovery_time_seconds,
            "total_cost_impact": str(metrics.budget_impact),
            "error_types": metrics.error_type_breakdown,
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics to zero."""
        with self._lock:
            self._error_count = 0
            self._retry_count = 0
            self._escalation_count = 0
            self._recovered_count = 0
            self._recovery_times = []
            self._error_types = {}
            self._budget_impact = Decimal("0.00")
