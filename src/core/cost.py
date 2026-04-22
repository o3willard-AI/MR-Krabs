#!/usr/bin/env python3
"""Enhanced cost tracking and budget management using Decimal for currency precision.

Implements a budget reservation pattern to prevent race conditions under concurrent access.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import json
import threading
import uuid


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

    def is_exceeded(self, current: Decimal) -> bool:
        return current >= self.daily_limit_usd

    def is_warning(self, current: Decimal) -> bool:
        return current >= (self.daily_limit_usd * self.warning_threshold)

    def is_emergency_exceeded(self, current: Decimal) -> bool:
        return current >= (self.daily_limit_usd + self.emergency_cap_usd)


class CostTracker:
    """Tracks costs and enforces budgets using Decimal for all monetary calculations.
    
    Uses a budget reservation pattern to prevent race conditions:
    1. reserve_budget() — atomically reserves budget before execution
    2. finalize_spending() — adjusts reservation to actual cost after execution
    3. release_reservation() — returns reserved budget on failure
    """
    
    MODEL_COSTS = {
        "qwen/qwen3.5-397b-a17b": {"prompt": Decimal("0.000001"), "completion": Decimal("0.000001")},
        "x-ai/grok-4.1-fast": {"prompt": Decimal("0.000002"), "completion": Decimal("0.000006")},
        "minimax/minimax-m2.7": {"prompt": Decimal("0.0000002"), "completion": Decimal("0.0000006")},
        "anthropic/claude-sonnet-4.6": {"prompt": Decimal("0.000003"), "completion": Decimal("0.000015")},
        "anthropic/claude-opus-4.6": {"prompt": Decimal("0.000015"), "completion": Decimal("0.000075")},
    }
    
    def __init__(self, budget: Optional[Budget] = None):
        self.budget = budget or Budget()
        self.entries: List[CostEntry] = []
        self.daily_total = Decimal("0.00")
        self.reserved_total = Decimal("0.00")
        self.task_totals: Dict[str, Decimal] = {}
        self.tier_totals: Dict[str, Decimal] = {}
        self._reservations: Dict[str, Reservation] = {}
        self._lock = threading.Lock()
        self._emergency_calls = 0
    
    def calculate_cost(
        self,
        model: str,
        tokens: TokenCount
    ) -> Decimal:
        """Calculate cost for given tokens and model using Decimal arithmetic."""
        pricing = self.MODEL_COSTS.get(model, {"prompt": Decimal("0.000001"), "completion": Decimal("0.000001")})
        
        prompt_cost = (Decimal(tokens.prompt_tokens) / Decimal("1000")) * pricing["prompt"]
        completion_cost = (Decimal(tokens.completion_tokens) / Decimal("1000")) * pricing["completion"]
        
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
                created_at=datetime.now(timezone.utc).isoformat(),
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
                timestamp=datetime.now(timezone.utc).isoformat(),
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
            
            if self.budget.is_warning(self.daily_total):
                print(f"Budget warning: ${self.daily_total:.4f} / ${self.budget.daily_limit_usd:.2f}")
            
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
        self,
        task_id: str,
        tier: str,
        model: str,
        tokens: TokenCount,
        duration: float
    ) -> CostEntry:
        """Record a cost entry (non-reservation path for simple sequential use)."""
        cost = self.calculate_cost(model, tokens)
        
        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            task_id=task_id,
            tier=tier,
            model=model,
            tokens=tokens,
            cost_usd=cost,
            duration_seconds=duration
        )
        
        self.entries.append(entry)
        self.daily_total += cost
        self.task_totals[task_id] = self.task_totals.get(task_id, Decimal("0.00")) + cost
        self.tier_totals[tier] = self.tier_totals.get(tier, Decimal("0.00")) + cost
        
        if self.budget.is_exceeded(self.daily_total):
            raise BudgetExceededError(
                f"Daily budget exceeded: ${self.daily_total:.4f} / ${self.budget.daily_limit_usd:.2f}"
            )
        
        if self.budget.is_warning(self.daily_total):
            print(f"Budget warning: ${self.daily_total:.4f} / ${self.budget.daily_limit_usd:.2f}")
        
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
    
    def get_summary(self) -> Dict:
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
                if self.budget.daily_limit_usd > 0 else Decimal("0")
            ),
            "task_totals": {k: float(v) for k, v in self.task_totals.items()},
            "tier_totals": {k: float(v) for k, v in self.tier_totals.items()},
            "total_requests": len(self.entries),
            "active_reservations": len(self._reservations),
        }
    
    def save_report(self, filepath: Optional[str] = None) -> Path:
        """Save cost report to JSON file."""
        if not filepath:
            filepath = f"cost_report_{datetime.now().strftime('%Y%m%d')}.json"
        
        report = {
            "generated": datetime.now(timezone.utc).isoformat(),
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
                        "total": e.tokens.total_tokens
                    },
                    "cost_usd": float(e.cost_usd),
                    "duration": e.duration_seconds
                }
                for e in self.entries
            ]
        }
        
        path = Path(filepath)
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return path


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""
    pass
