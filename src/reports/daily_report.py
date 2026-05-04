"""
Cost reporting module for daily reports and analysis.
Part of P4-5: Daily Cost Reporting.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from src.core.cost import CostTracker, CostEntry


@dataclass
class DailyCostReport:
    """Daily cost report with breakdowns and statistics."""
    
    date: date
    """Date for this report."""
    
    total_cost: Decimal
    """Total cost for the day."""
    
    task_count: int
    """Number of tasks executed."""
    
    tier_breakdown: dict[str, Decimal]
    """Cost breakdown by tier (tier_name -> cost)."""
    
    model_breakdown: dict[str, Decimal]
    """Cost breakdown by model (model_name -> cost)."""
    
    def to_dict(self) -> dict:
        """Convert report to dictionary for serialization."""
        # Calculate percentages
        tier_percentages = {}
        if self.total_cost > 0:
            for tier, cost in self.tier_breakdown.items():
                tier_percentages[tier] = round(float(cost / self.total_cost * 100), 2)
        
        model_percentages = {}
        if self.total_cost > 0:
            for model, cost in self.model_breakdown.items():
                model_percentages[model] = round(float(cost / self.total_cost * 100), 2)
        
        # Convert Decimal values to strings for JSON serialization
        tier_breakdown_str = {k: str(v) for k, v in self.tier_breakdown.items()}
        model_breakdown_str = {k: str(v) for k, v in self.model_breakdown.items()}
        
        return {
            "date": self.date.isoformat(),
            "total_cost": str(self.total_cost),
            "task_count": self.task_count,
            "tier_breakdown": tier_breakdown_str,
            "tier_percentages": tier_percentages,
            "model_breakdown": model_breakdown_str,
            "model_percentages": model_percentages,
        }
    
    def __str__(self) -> str:
        """Generate a formatted text report."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  Daily Cost Report - {self.date}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  Total Cost:    ${self.total_cost:.2f}")
        lines.append(f"  Task Count:    {self.task_count:,}")
        if self.task_count > 0:
            lines.append(f"  Avg/Task:      ${self.total_cost / self.task_count:.4f}")
        lines.append("")
        lines.append("  Tier Breakdown:")
        for tier, cost in sorted(self.tier_breakdown.items(), 
                                  key=lambda x: x[1], reverse=True):
            pct = float(cost / self.total_cost * 100) if self.total_cost > 0 else 0
            lines.append(f"    {tier:15s}  ${cost:>10.2f}  ({pct:5.1f}%)")
        lines.append("")
        lines.append("  Model Breakdown:")
        for model, cost in sorted(self.model_breakdown.items(),
                                   key=lambda x: x[1], reverse=True):
            pct = float(cost / self.total_cost * 100) if self.total_cost > 0 else 0
            lines.append(f"    {model:25s}  ${cost:>10.2f}  ({pct:5.1f}%)")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


class DailyCostReportGenerator:
    """
    Generates daily cost reports with formatting and analysis.
    
    Provides methods to:
    - Generate formatted daily reports
    - Format cost summaries
    - Format tier breakdowns
    - Create budget status reports
    """
    
    def __init__(self, tracker: Optional[CostTracker] = None):
        """
        Initialize the report generator.
        
        Args:
            tracker: Optional CostTracker instance to generate reports from
        """
        self.tracker = tracker
    
    def generate_report(self, report_date: date) -> DailyCostReport:
        """
        Generate a DailyCostReport for a specific date.
        
        Args:
            report_date: The date to generate the report for
            
        Returns:
            DailyCostReport instance with data for the specified date
        """
        if not self.tracker:
            return DailyCostReport(
                date=report_date,
                total_cost=Decimal("0.00"),
                task_count=0,
                tier_breakdown={},
                model_breakdown={}
            )
        
        # Filter entries for the specified date
        entries_for_date = []
        for entry in self.tracker.entries:
            entry_date = datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00')).date()
            if entry_date == report_date:
                entries_for_date.append(entry)
        
        if not entries_for_date:
            return DailyCostReport(
                date=report_date,
                total_cost=Decimal("0.00"),
                task_count=0,
                tier_breakdown={},
                model_breakdown={}
            )
        
        # Calculate totals and breakdowns
        total_cost = Decimal("0.00")
        tier_breakdown: dict[str, Decimal] = {}
        model_breakdown: dict[str, Decimal] = {}
        
        for entry in entries_for_date:
            cost = entry.cost_usd
            total_cost += cost
            
            # Accumulate by tier
            if entry.tier not in tier_breakdown:
                tier_breakdown[entry.tier] = Decimal("0.00")
            tier_breakdown[entry.tier] += cost
            
            # Accumulate by model
            if entry.model not in model_breakdown:
                model_breakdown[entry.model] = Decimal("0.00")
            model_breakdown[entry.model] += cost
        
        return DailyCostReport(
            date=report_date,
            total_cost=total_cost,
            task_count=len(entries_for_date),
            tier_breakdown=tier_breakdown,
            model_breakdown=model_breakdown
        )
    
    def generate(self, 
                 summary: dict,
                 daily_limit: Decimal,
                 warning_threshold: Decimal = Decimal("0.80"),
                 days: int = 1) -> str:
        """
        Generate a formatted daily report.
        
        Args:
            summary: Cost summary dictionary
            daily_limit: Daily budget limit
            warning_threshold: Warning threshold (default 80%)
            days: Number of days to report on
        
        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"  Cost-Optimized Orchestrator - Daily Report")
        lines.append(f"  Period: Last {days} day(s)")
        lines.append("=" * 60)
        lines.append("")
        
        # Budget status
        total_cost = summary.get('total_cost', Decimal("0.00"))
        budget_pct = total_cost / daily_limit if daily_limit > 0 else Decimal("0.00")
        
        lines.append("Budget Status:")
        lines.append("-" * 40)
        lines.append(f"  Daily Limit:      ${daily_limit:.2f}")
        lines.append(f"  Current Spend:    ${total_cost:.2f}")
        lines.append(f"  Budget Used:      {budget_pct:.1%}")
        
        if budget_pct >= Decimal("0.95"):
            lines.append("  ⚠️  CRITICAL: Over 95% of daily budget used!")
        elif budget_pct >= warning_threshold:
            lines.append("  ⚠️  WARNING: Over 80% of daily budget used!")
        lines.append("")
        
        # Task summary
        task_count = summary.get('total_tasks', 0)
        lines.append("Task Summary:")
        lines.append("-" * 40)
        lines.append(f"  Total Tasks:      {task_count:,}")
        if task_count > 0:
            avg_cost = total_cost / Decimal(task_count)
            lines.append(f"  Avg Cost/Task:    ${avg_cost:.4f}")
        lines.append("")
        
        # Tier breakdown
        cost_by_tier = summary.get('cost_by_tier', {})
        if cost_by_tier:
            lines.append("Tier Breakdown:")
            lines.append("-" * 40)
            for tier, cost in sorted(cost_by_tier.items(), 
                                      key=lambda x: x[1], reverse=True):
                pct = float(cost / total_cost * 100) if total_cost > 0 else 0
                lines.append(f"  {tier:15s}  ${cost:>10.2f}  ({pct:5.1f}%)")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_cost_summary(self, 
                            total_cost: Decimal,
                            task_count: int,
                            cost_by_tier: Optional[dict[str, Decimal]] = None) -> str:
        """
        Format a cost summary string.
        
        Args:
            total_cost: Total cost
            task_count: Total task count
            cost_by_tier: Optional tier breakdown
        
        Returns:
            Formatted summary string
        """
        lines = []
        lines.append(f"Total Cost: ${total_cost:.2f}")
        lines.append(f"Tasks: {task_count:,}")
        
        if task_count > 0:
            avg = total_cost / Decimal(task_count)
            lines.append(f"Avg/Task: ${avg:.4f}")
        
        if cost_by_tier:
            lines.append("")
            lines.append("By Tier:")
            for tier, cost in sorted(cost_by_tier.items(),
                                      key=lambda x: x[1], reverse=True):
                pct = float(cost / total_cost * 100) if total_cost > 0 else 0
                lines.append(f"  {tier}: ${cost:.2f} ({pct:.1f}%)")
        
        return "\n".join(lines)
    
    def format_tier_breakdown(self, 
                              cost_by_tier: dict[str, Decimal],
                              total_cost: Optional[Decimal] = None) -> str:
        """
        Format a tier breakdown string.
        
        Args:
            cost_by_tier: Cost by tier dictionary
            total_cost: Optional total for percentage calculation
        
        Returns:
            Formatted tier breakdown string
        """
        if not cost_by_tier:
            return "No tier data available"
        
        if total_cost is None:
            total_cost = sum(cost_by_tier.values())
        
        lines = []
        lines.append("Tier Breakdown:")
        for tier, cost in sorted(cost_by_tier.items(),
                                  key=lambda x: x[1], reverse=True):
            pct = float(cost / total_cost * 100) if total_cost > 0 else 0
            lines.append(f"  {tier:15s}  ${cost:>10.2f}  ({pct:5.1f}%)")
        
        return "\n".join(lines)
