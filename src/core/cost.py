#!/usr/bin/env python3
"""Enhanced cost tracking and budget management using Decimal for currency precision.

Implements a budget reservation pattern to prevent race conditions under concurrent access.
"""

import csv
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Callable, Optional


@dataclass
class TokenCount:
    """Token count for a request/response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class CostEntry:
    """Single cost entry."""

    timestamp: str
    task_id: str
    tier: str
    model: str
    tokens: TokenCount
    cost_usd: Decimal
    duration_seconds: float


@dataclass
class Reservation:
    """A budget reservation returned by reserve_budget()."""

    id: str
    scope: str
    amount: Decimal
    created_at: str


class FailureMode(Enum):
    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN_WITH_ALERT = "fail_open_with_alert"


@dataclass
class Budget:
    """Budget configuration."""
    
    daily_limit_usd: Decimal = Decimal("10.00")
    task_limit_usd: Decimal = Decimal("1.00")
    warning_threshold: Decimal = Decimal("0.8")
    failure_mode: FailureMode = FailureMode.FAIL_OPEN_WITH_ALERT
    emergency_cap_usd: Decimal = Decimal("5.00")
    emergency_call_limit: int = 10
    warn_thresholds: list[Decimal] = field(default_factory=lambda: [Decimal("0.5"), Decimal("0.75"), Decimal("0.9")])

    def is_exceeded(self, current: Decimal) -> bool:
        return current >= self.daily_limit_usd

    def is_warning(self, current: Decimal) -> bool:
        return current >= (self.daily_limit_usd * self.warning_threshold)

    def is_emergency_exceeded(self, current: Decimal) -> bool:
        return current >= (self.daily_limit_usd + self.emergency_cap_usd)
    
    def get_warning_level(self, current: Decimal) -> Optional[Decimal]:
        """Return the highest warning threshold exceeded, or None."""
        for threshold in reversed(self.warn_thresholds):
            if current >= (self.daily_limit_usd * threshold):
                return threshold
        return None


class CostTracker:
    """Tracks costs and enforces budgets using Decimal for all monetary calculations.

    Uses a budget reservation pattern to prevent race conditions:
    1. reserve_budget() — atomically reserves budget before execution
    2. finalize_spending() — adjusts reservation to actual cost after execution
    3. release_reservation() — returns reserved budget on failure
    """

    MODEL_COSTS = {
        "qwen/qwen3.5-397b-a17b": {
            "prompt": Decimal("0.000001"),
            "completion": Decimal("0.000001"),
        },
        "x-ai/grok-4.1-fast": {"prompt": Decimal("0.000002"), "completion": Decimal("0.000006")},
        "minimax/minimax-m2.7": {
            "prompt": Decimal("0.0000002"),
            "completion": Decimal("0.0000006"),
        },
        "anthropic/claude-sonnet-4.6": {
            "prompt": Decimal("0.000003"),
            "completion": Decimal("0.000015"),
        },
        "anthropic/claude-opus-4.6": {
            "prompt": Decimal("0.000015"),
            "completion": Decimal("0.000075"),
        },
        "google/gemma-4-31b-it": {
            "prompt": Decimal("0.000001"),
            "completion": Decimal("0.000002"),
        },
        "meta-llama/llama-3.3-70b": {
            "prompt": Decimal("0.0000002"),
            "completion": Decimal("0.0000008"),
        },
    }

    def __init__(self, budget: Budget | None = None):
        self.budget = budget or Budget()
        self.entries: list[CostEntry] = []
        self.daily_total = Decimal("0.00")
        self.reserved_total = Decimal("0.00")
        self.task_totals: dict[str, Decimal] = {}
        self.tier_totals: dict[str, Decimal] = {}
        self._reservations: dict[str, Reservation] = {}
        self._lock = threading.Lock()
        self._emergency_calls = 0
        
        # Warning tracking for P1-5
        self._warning_shown_today = False
        self._emergency_shown_today = False
        self._current_date = datetime.now(UTC).date()
        
        # Cost alert handler for P4-1
        self.alert_handler = CostAlertHandler()
        
        # Track warning levels shown today
        self._warning_levels_shown: set[str] = set()

    def _check_and_reset_daily_flags(self):
        """Reset warning flags if new day."""
        today = datetime.now(UTC).date()
        if today != self._current_date:
            self._warning_shown_today = False
            self._emergency_shown_today = False
            self._current_date = today
            self._warning_levels_shown = set()

    def _emit_warning(self, level: str = "warning"):
        """Emit budget warning if not already shown today."""
        self._check_and_reset_daily_flags()
        
        if level == "warning" and self._warning_shown_today:
            return
        
        if level == "emergency" and self._emergency_shown_today:
            return
        
        if level == "warning":
            # P4-1: Multi-level warnings using alert handler
            warning_level = self.budget.get_warning_level(self.daily_total)
            if warning_level is None:
                return
            
            # Determine alert type
            if warning_level == Decimal("0.5"):
                alert_type = "warning_50"
            elif warning_level == Decimal("0.75"):
                alert_type = "warning_75"
            elif warning_level == Decimal("0.9"):
                alert_type = "warning_90"
            else:
                alert_type = "warning"
            
            # Only show each level once per day
            if alert_type in self._warning_levels_shown:
                return
            
            self._warning_levels_shown.add(alert_type)
            self.alert_handler.handle_warning(alert_type, self)
        
        elif level == "emergency":
            emergency_threshold = self.budget.daily_limit_usd + self.budget.emergency_cap_usd
            if self.budget.daily_limit_usd > 0 and self.daily_total >= emergency_threshold:
                if not self._emergency_shown_today:
                    self._emergency_shown_today = True
                    self.alert_handler.handle_warning("emergency", self)

    def calculate_cost(self, model: str, tokens: TokenCount) -> Decimal:
        """Calculate cost for given tokens and model using Decimal arithmetic."""
        pricing = self.MODEL_COSTS.get(
            model, {"prompt": Decimal("0.000001"), "completion": Decimal("0.000001")}
        )

        prompt_cost = (Decimal(tokens.prompt_tokens) / Decimal("1000")) * pricing["prompt"]
        completion_cost = (Decimal(tokens.completion_tokens) / Decimal("1000")) * pricing[
            "completion"
        ]

        return prompt_cost + completion_cost

    def reserve_budget(self, scope: str, estimated_cost: Decimal) -> Reservation:
        """Atomically reserve budget. Returns reservation or raises BudgetExceededError.

        This prevents the check-then-act race condition where two concurrent tasks
        both pass the budget check and both execute, exceeding the budget.

        Also enforces per-task cost limits via budget.task_limit_usd.

        Args:
            scope: Budget scope (e.g. "daily", "task-42").
            estimated_cost: Estimated cost to reserve.

        Returns:
            Reservation object with id to use in finalize_spending or release_reservation.

        Raises:
            BudgetExceededError: If reserved + actual spending would exceed budget,
                or if estimated_cost exceeds per-task limit.
        """
        with self._lock:
            if estimated_cost > self.budget.task_limit_usd:
                raise BudgetExceededError(
                    f"Task cost ${float(estimated_cost):.4f} exceeds per-task limit "
                    f"of ${float(self.budget.task_limit_usd):.2f}"
                )

            effective_total = self.daily_total + self.reserved_total
            if effective_total + estimated_cost > self.budget.daily_limit_usd:
                raise BudgetExceededError(
                    f"Budget reservation failed: ${effective_total + estimated_cost:.4f} "
                    f"would exceed limit of ${self.budget.daily_limit_usd:.2f} "
                    f"(spent: ${self.daily_total:.4f}, reserved: ${self.reserved_total:.4f})"
                )

            reservation_id = str(uuid.uuid4())[:12]
            reservation = Reservation(
                id=reservation_id,
                scope=scope,
                amount=estimated_cost,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._reservations[reservation_id] = reservation
            self.reserved_total += estimated_cost
            return reservation

    def finalize_spending(self, reservation_id: str, actual_cost: Decimal) -> CostEntry:
        """Finalize a reservation with the actual cost.

        Adjusts the reservation to the actual cost and records the spending.
        If actual_cost > reserved amount, the difference is added to daily_total.
        If actual_cost < reserved amount, the surplus is released.

        Args:
            reservation_id: ID from reserve_budget().
            actual_cost: Actual cost incurred.

        Returns:
            CostEntry for the finalized spending.

        Raises:
            KeyError: If reservation_id is not found.
        """
        with self._lock:
            if reservation_id not in self._reservations:
                raise KeyError(f"Reservation not found: {reservation_id}")

            reservation = self._reservations.pop(reservation_id)
            self.reserved_total -= reservation.amount

            self.daily_total += actual_cost
            self.task_totals[reservation.scope] = (
                self.task_totals.get(reservation.scope, Decimal("0.00")) + actual_cost
            )

            entry = CostEntry(
                timestamp=datetime.now(UTC).isoformat(),
                task_id=reservation.scope,
                tier="",
                model="",
                tokens=TokenCount(),
                cost_usd=actual_cost,
                duration_seconds=0.0,
            )
            self.entries.append(entry)

            if self.budget.is_exceeded(self.daily_total):
                raise BudgetExceededError(
                    f"Daily budget exceeded after finalization: "
                    f"${self.daily_total:.4f} / ${self.budget.daily_limit_usd:.2f}"
                )
            
            # P1-5: Emit budget warning if at warning threshold
            if self.budget.is_warning(self.daily_total):
                self._emit_warning("warning")
            
            # P1-5: Emit emergency warning if exceeded
            if self.budget.is_emergency_exceeded(self.daily_total):
                self._emit_warning("emergency")
            
            return entry

    def release_reservation(self, reservation_id: str) -> None:
        """Release a reservation without recording spending.

        Called when a task fails or is cancelled before execution completes.

        Args:
            reservation_id: ID from reserve_budget().
        """
        with self._lock:
            if reservation_id in self._reservations:
                reservation = self._reservations.pop(reservation_id)
                self.reserved_total -= reservation.amount

    def record(
        self, task_id: str, tier: str, model: str, tokens: TokenCount, duration: float
    ) -> CostEntry:
        """Record a cost entry (non-reservation path for simple sequential use)."""
        cost = self.calculate_cost(model, tokens)

        entry = CostEntry(
            timestamp=datetime.now(UTC).isoformat(),
            task_id=task_id,
            tier=tier,
            model=model,
            tokens=tokens,
            cost_usd=cost,
            duration_seconds=duration,
        )

        self.entries.append(entry)
        self.daily_total += cost
        self.task_totals[task_id] = self.task_totals.get(task_id, Decimal("0.00")) + cost
        self.tier_totals[tier] = self.tier_totals.get(tier, Decimal("0.00")) + cost

        if self.budget.is_exceeded(self.daily_total):
            raise BudgetExceededError(
                f"Daily budget exceeded: ${self.daily_total:.4f} / "
                f"${self.budget.daily_limit_usd:.2f}"
            )

        # P4-1: Use multi-level warning system
        self._emit_warning("warning")

        return entry

    def get_daily_total(self) -> Decimal:
        """Get total cost for current session (excluding reservations)."""
        return self.daily_total

    def get_effective_total(self) -> Decimal:
        """Get total including both spent and reserved budget."""
        return self.daily_total + self.reserved_total

    def get_task_total(self, task_id: str) -> Decimal:
        """Get total cost for specific task."""
        return self.task_totals.get(task_id, Decimal("0.00"))

    def get_summary(self) -> dict:
        """Get cost summary with Decimal values converted to float for serialization."""
        effective = self.daily_total + self.reserved_total
        return {
            "daily_total": float(self.daily_total),
            "reserved_total": float(self.reserved_total),
            "effective_total": float(effective),
            "budget_limit": float(self.budget.daily_limit_usd),
            "budget_remaining": float(self.budget.daily_limit_usd - effective),
            "budget_used_percent": float(
                (effective / self.budget.daily_limit_usd * Decimal("100"))
                if self.budget.daily_limit_usd > 0
                else Decimal("0")
            ),
            "task_totals": {k: float(v) for k, v in self.task_totals.items()},
            "tier_totals": {k: float(v) for k, v in self.tier_totals.items()},
            "total_requests": len(self.entries),
            "active_reservations": len(self._reservations),
        }

    def save_report(self, filepath: str | None = None) -> Path:
        """Save cost report to JSON file."""
        if not filepath:
            filepath = f"cost_report_{datetime.now().strftime('%Y%m%d')}.json"
        
        report = {
            "generated": datetime.now(UTC).isoformat(),
            "summary": self.get_summary(),
            "entries": [
                {
                    "timestamp": e.timestamp,
                    "task_id": e.task_id,
                    "tier": e.tier,
                    "model": e.model,
                    "tokens": {
                        "prompt": e.tokens.prompt_tokens,
                        "completion": e.tokens.completion_tokens,
                        "total": e.tokens.total_tokens,
                    },
                    "cost_usd": float(e.cost_usd),
                    "duration": e.duration_seconds,
                }
                for e in self.entries
            ],
        }
        
        path = Path(filepath)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        
        return path
    
    def export_csv(self, filepath: str | None = None) -> Path:
        """Export cost data to CSV file.
        
        P1-6: CSV export for cost analysis
        """
        if not filepath:
            filepath = f"cost_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
        path = Path(filepath)
        
        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'task_id', 'tier', 'model', 
                'prompt_tokens', 'completion_tokens', 'total_tokens',
                'cost_usd', 'duration_seconds'
            ])
            
            for entry in self.entries:
                writer.writerow([
                    entry.timestamp,
                    entry.task_id,
                    entry.tier,
                    entry.model,
                    entry.tokens.prompt_tokens,
                    entry.tokens.completion_tokens,
                    entry.tokens.total_tokens,
                    float(entry.cost_usd),
                    entry.duration_seconds
                ])
        
        return path
    
    def add_alert_callback(self, callback: Callable) -> None:
        """Register a callback to be invoked on cost alerts.
        
        P4-1: Real-time cost alert callbacks
        """
        self.alert_handler.add_callback(callback)
    
    def get_alert_history(self) -> list:
        """Get list of all cost alerts generated."""
        return self.alert_handler.alert_history.copy()


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""
    pass


@dataclass
class CostAlert:
    """Represents a cost alert event."""
    timestamp: str
    alert_type: str  # 'warning', 'warning_50', 'warning_75', 'warning_90', 'emergency'
    daily_total: Decimal
    budget_limit: Decimal
    percentage: Decimal
    message: str


class CostAlertHandler:
    """Handles cost alerts with configurable callbacks."""
    
    def __init__(self):
        self.callbacks: list[Callable[[CostAlert], None]] = []
        self.alert_history: list[CostAlert] = []
    
    def add_callback(self, callback: Callable[[CostAlert], None]) -> None:
        """Add a callback to be invoked on alerts."""
        self.callbacks.append(callback)
    
    def _invoke_callbacks(self, alert: CostAlert) -> None:
        """Invoke all registered callbacks with the alert."""
        for callback in self.callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"[COST_ALERT] Error invoking callback: {e}")
    
    def _create_alert(self, alert_type: str, tracker: 'CostTracker') -> CostAlert:
        """Create a CostAlert object."""
        daily_total = tracker.get_daily_total()
        budget_limit = tracker.budget.daily_limit_usd
        percentage = (daily_total / budget_limit * Decimal("100")) if budget_limit > 0 else Decimal("0")
        
        messages = {
            "warning_50": f"\n[BUDGET WARNING - 50%] ${float(daily_total):.4f} / ${float(budget_limit):.2f} ({float(percentage):.1f}%)",
            "warning_75": f"\n[BUDGET WARNING - 75%] ${float(daily_total):.4f} / ${float(budget_limit):.2f} ({float(percentage):.1f}%)",
            "warning_90": f"\n[BUDGET WARNING - 90%] ${float(daily_total):.4f} / ${float(budget_limit):.2f} ({float(percentage):.1f}%)",
            "warning": f"\n[BUDGET WARNING - {float(percentage):.1f}%] ${float(daily_total):.4f} / ${float(budget_limit):.2f}",
            "emergency": f"\n*** EMERGENCY BUDGET ALERT *** ${float(daily_total):.4f} / ${float(budget_limit):.2f} ***",
        }
        
        return CostAlert(
            timestamp=datetime.now(UTC).isoformat(),
            alert_type=alert_type,
            daily_total=daily_total,
            budget_limit=budget_limit,
            percentage=percentage,
            message=messages.get(alert_type, messages["warning"])
        )
    
    def handle_warning(self, alert_type: str, tracker: 'CostTracker') -> None:
        """Handle a budget warning alert."""
        alert = self._create_alert(alert_type, tracker)
        self.alert_history.append(alert)
        self._invoke_callbacks(alert)
        print(alert.message)
