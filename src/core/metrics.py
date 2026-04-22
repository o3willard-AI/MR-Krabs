#!/usr/bin/env python3
"""Metrics collection for orchestrator operations."""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


@dataclass
class TaskMetrics:
    """Metrics for a single task execution."""
    task_id: str
    tier: str
    timestamp: str
    success: bool
    duration_seconds: float
    attempts: int
    tools_executed: int
    tools_succeeded: int
    tokens_estimate: int = 0
    cost_estimate_usd: float = 0.0


@dataclass
class TierMetrics:
    """Aggregated metrics for a tier."""
    tier: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_duration: float = 0.0
    total_attempts: int = 0
    total_tools: int = 0
    total_cost: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks
    
    @property
    def avg_duration(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_duration / self.total_tasks
    
    @property
    def avg_attempts(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_attempts / self.total_tasks


class MetricsCollector:
    """Collects and aggregates orchestrator metrics."""
    
    TIER_COSTS = {
        "L0-Planner": 0.000001,
        "L0-Reviewer": 0.000001,
        "L0-Coder": 0.0,
        "L1-Coder": 0.000002,
        "L2-Coder": 0.000003,
        "L3-Coder": 0.00001,
        "L3-Architect": 0.00002
    }
    
    def __init__(self, metrics_dir: str = None):
        if metrics_dir:
            self.metrics_dir = Path(metrics_dir)
        else:
            self.metrics_dir = Path(__file__).parent.parent.parent / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.task_metrics: List[TaskMetrics] = []
        self.tier_metrics: Dict[str, TierMetrics] = {}
        self.start_time = datetime.now(timezone.utc)
    
    def record_task(
        self,
        task_id: str,
        tier: str,
        success: bool,
        duration: float,
        attempts: int,
        tools_executed: int = 0,
        tools_succeeded: int = 0,
        tokens: int = 0
    ) -> TaskMetrics:
        """Record metrics for a task execution."""
        cost = self.TIER_COSTS.get(tier, 0.0) * tokens
        
        metrics = TaskMetrics(
            task_id=task_id,
            tier=tier,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=success,
            duration_seconds=duration,
            attempts=attempts,
            tools_executed=tools_executed,
            tools_succeeded=tools_succeeded,
            tokens_estimate=tokens,
            cost_estimate_usd=cost
        )
        
        self.task_metrics.append(metrics)
        
        if tier not in self.tier_metrics:
            self.tier_metrics[tier] = TierMetrics(tier=tier)
        
        tm = self.tier_metrics[tier]
        tm.total_tasks += 1
        if success:
            tm.successful_tasks += 1
        else:
            tm.failed_tasks += 1
        tm.total_duration += duration
        tm.total_attempts += attempts
        tm.total_tools += tools_executed
        tm.total_cost += cost
        
        return metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        total_cost = sum(tm.total_cost for tm in self.tier_metrics.values())
        total_tasks = sum(tm.total_tasks for tm in self.tier_metrics.values())
        total_success = sum(tm.successful_tasks for tm in self.tier_metrics.values())
        
        return {
            "session_start": self.start_time.isoformat(),
            "total_tasks": total_tasks,
            "successful_tasks": total_success,
            "failed_tasks": total_tasks - total_success,
            "overall_success_rate": total_success / total_tasks if total_tasks > 0 else 0.0,
            "total_cost_usd": total_cost,
            "tiers": {
                tier: {
                    "tasks": tm.total_tasks,
                    "success_rate": tm.success_rate,
                    "avg_duration": tm.avg_duration,
                    "avg_attempts": tm.avg_attempts,
                    "cost": tm.total_cost
                }
                for tier, tm in self.tier_metrics.items()
            }
        }
    
    def save_metrics(self, filename: str = None) -> Path:
        """Save metrics to JSON file."""
        if not filename:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.metrics_dir / filename
        data = {
            "summary": self.get_summary(),
            "tier_metrics": [asdict(tm) for tm in self.tier_metrics.values()],
            "task_metrics": [asdict(tm) for tm in self.task_metrics[-100:]]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        return filepath
    
    def print_summary(self):
        """Print metrics summary to console."""
        summary = self.get_summary()
        
        print("\n" + "=" * 60)
        print("METRICS SUMMARY")
        print("=" * 60)
        print(f"Total Tasks: {summary['total_tasks']}")
        print(f"Success Rate: {summary['overall_success_rate']:.1%}")
        print(f"Estimated Cost: ${summary['total_cost_usd']:.4f}")
        print()
        print("By Tier:")
        for tier, data in summary['tiers'].items():
            print(f"  {tier}:")
            print(f"    Tasks: {data['tasks']}, Success: {data['success_rate']:.1%}")
            print(f"    Avg Duration: {data['avg_duration']:.1f}s, Avg Attempts: {data['avg_attempts']:.1f}")
        print("=" * 60)
