"""
TrendAnalysis module for cost trend detection and analysis.

P4-5: Daily Cost Reporting - Trend Analysis
=============================================

This module provides analysis of cost trends including:
- Day-over-day change detection
- Week-over-week comparisons
- Spending spike detection
- Cost trend recommendations
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional


@dataclass
class TrendAnalysis:
    """
    Analysis results for cost trends.
    
    Attributes:
        period_start: Start date of the analysis period
        period_end: End date of the analysis period
        total_cost: Total cost over the period
        task_count: Total number of tasks
        avg_daily_cost: Average daily cost
        day_over_day_change: Day-over-day percentage change
        week_over_week_change: Week-over-week percentage change
        has_spending_spike: Whether a spending spike was detected (>50% increase)
    """
    period_start: date
    period_end: date
    total_cost: Decimal
    task_count: int
    avg_daily_cost: Decimal
    day_over_day_change: Decimal
    week_over_week_change: Decimal
    has_spending_spike: bool


class TrendAnalyzer:
    """
    Analyzer for detecting and analyzing cost trends.
    
    Provides methods to:
    - Analyze 7-day and 30-day trends
    - Detect spending spikes
    - Calculate day-over-day and week-over-week changes
    - Generate trend-based recommendations
    """
    
    # Spike detection threshold
    SPIKE_THRESHOLD = Decimal("0.50")  # 50% increase triggers spike alert
    
    # Trend thresholds for recommendations
    INCREASING_THRESHOLD = Decimal("0.10")  # >10% increase is concerning
    DECREASING_THRESHOLD = Decimal("-0.10")  # <-10% decrease is positive
    
    def analyze_7_day_trend(self, daily_costs: List[Decimal], task_counts: Optional[List[int]] = None) -> TrendAnalysis:
        """
        Analyze 7-day cost trend.
        
        Args:
            daily_costs: List of daily costs (minimum 2 values, oldest to newest)
            task_counts: Optional list of daily task counts
        
        Returns:
            TrendAnalysis for the period
        """
        if len(daily_costs) < 2:
            raise ValueError(f"Expected at least 2 daily costs, got {len(daily_costs)}")
        
        n = len(daily_costs)
        period_start = date.today() - timedelta(days=n-1)
        period_end = date.today()
        
        total_cost = sum(daily_costs)
        avg_daily_cost = total_cost / Decimal(n)
        
        # Calculate day-over-day change (comparing first to last for trend)
        day_over_day_change = self._calculate_extended_day_over_day_change(daily_costs)
        
        # Detect spending spike (last day vs second-to-last)
        has_spike = self._calculate_day_over_day_change(daily_costs[-2], daily_costs[-1]) > self.SPIKE_THRESHOLD
        
        # For shorter periods, week-over-week is not applicable
        week_over_week_change = Decimal("0.00") if n < 14 else self._calculate_week_over_week_change(
            sum(daily_costs[n-14:n-7]), sum(daily_costs[n-7:n])
        )
        
        # Calculate task count if provided
        task_count = sum(task_counts) if task_counts else 0
        
        return TrendAnalysis(
            period_start=period_start,
            period_end=period_end,
            total_cost=total_cost,
            task_count=task_count,
            avg_daily_cost=avg_daily_cost,
            day_over_day_change=day_over_day_change,
            week_over_week_change=week_over_week_change,
            has_spending_spike=has_spike
        )
    
    def analyze_30_day_trend(self, daily_costs: List[Decimal], 
                            task_counts: Optional[List[int]] = None) -> TrendAnalysis:
        """
        Analyze 30-day cost trend.
        
        Args:
            daily_costs: List of daily costs (30 values, oldest to newest)
            task_counts: Optional list of daily task counts
        
        Returns:
            TrendAnalysis for the 30-day period
        """
        if len(daily_costs) != 30:
            raise ValueError(f"Expected 30 daily costs, got {len(daily_costs)}")
        
        period_start = date.today() - timedelta(days=29)
        period_end = date.today()
        
        total_cost = sum(daily_costs)
        avg_daily_cost = total_cost / Decimal("30")
        
        # Calculate day-over-day change
        day_over_day_change = self._calculate_day_over_day_change(
            daily_costs[-2], daily_costs[-1]
        )
        
        # Calculate week-over-week change (compare last 7 days to previous 7 days)
        last_7_days = daily_costs[-7:]
        previous_7_days = daily_costs[-14:-7]
        
        last_week_total = sum(last_7_days)
        previous_week_total = sum(previous_7_days)
        
        week_over_week_change = self._calculate_week_over_week_change(
            previous_week_total, last_week_total
        )
        
        # Detect spending spike
        has_spike = day_over_day_change > self.SPIKE_THRESHOLD
        
        # Calculate task count if provided
        task_count = sum(task_counts) if task_counts else 0
        
        return TrendAnalysis(
            period_start=period_start,
            period_end=period_end,
            total_cost=total_cost,
            task_count=task_count,
            avg_daily_cost=avg_daily_cost,
            day_over_day_change=day_over_day_change,
            week_over_week_change=week_over_week_change,
            has_spending_spike=has_spike
        )
    
    def _calculate_extended_day_over_day_change(self, daily_costs: List[Decimal]) -> Decimal:
        """
        Calculate extended day-over-day change (first day to last day).
        Useful for detecting overall trend rather than single-day volatility.
        
        Args:
            daily_costs: List of daily costs (oldest to newest)
        
        Returns:
            Percentage change from first to last day
        """
        if len(daily_costs) < 2:
            return Decimal("0.00")
        
        first_day = daily_costs[0]
        last_day = daily_costs[-1]
        
        if first_day == Decimal("0.00"):
            if last_day > Decimal("0.00"):
                return Decimal("1.00")  # 100% increase from zero
            return Decimal("0.00")
        
        change = (last_day - first_day) / first_day
        return round(change, 4)
    
    def _calculate_day_over_day_change(self, previous_value: Decimal, 
                                       current_value: Decimal) -> Decimal:
        """
        Calculate day-over-day percentage change.
        
        Args:
            previous_value: Value from previous period
            current_value: Value from current period
        
        Returns:
            Percentage change (e.g., 0.25 for 25% increase)
        """
        if previous_value == Decimal("0.00"):
            if current_value > Decimal("0.00"):
                return Decimal("1.00")  # 100% increase from zero
            return Decimal("0.00")
        
        change = (current_value - previous_value) / previous_value
        return round(change, 4)
    
    def _calculate_week_over_week_change(self, last_week_total: Decimal,
                                         this_week_total: Decimal) -> Decimal:
        """
        Calculate week-over-week percentage change.
        
        Args:
            last_week_total: Total cost for last week
            this_week_total: Total cost for this week
        
        Returns:
            Percentage change
        """
        if last_week_total == Decimal("0.00"):
            if this_week_total > Decimal("0.00"):
                return Decimal("1.00")
            return Decimal("0.00")
        
        change = (this_week_total - last_week_total) / last_week_total
        return round(change, 4)
    
    def analyze_tier_trends(self, tier_daily_costs: Dict[str, List[Decimal]]) -> Dict[str, TrendAnalysis]:
        """
        Analyze trends for each tier separately.
        
        Args:
            tier_daily_costs: Dictionary mapping tier names to daily cost lists
        
        Returns:
            Dictionary of tier name to TrendAnalysis
        """
        results = {}
        
        for tier_name, daily_costs in tier_daily_costs.items():
            if len(daily_costs) >= 2:
                results[tier_name] = self.analyze_7_day_trend(daily_costs[-7:] if len(daily_costs) > 7 else daily_costs)
        
        return results
    
    def generate_trend_recommendations(self, 
                                       analysis: TrendAnalysis) -> List[Dict[str, Any]]:
        """
        Generate recommendations based on trend analysis.
        
        Args:
            analysis: TrendAnalysis object
            tier_analyses: Optional tier-specific analysis data
        
        Returns:
            List of recommendation dictionaries
        """
        recommendations = []
        
        # Spike alert
        if analysis.has_spending_spike:
            recommendations.append({
                "message": f"⚠️ Spending spike detected! Costs increased by {analysis.day_over_day_change:.0%} "
                          f"compared to yesterday. Total: ${analysis.avg_daily_cost:.2f}/day average.",
                "priority": "high",
                "type": "spike_alert"
            })
        
        # Day-over-day trend
        if analysis.day_over_day_change > self.INCREASING_THRESHOLD:
            recommendations.append({
                "message": f"📈 Costs are increasing ({analysis.day_over_day_change:+.0%} vs yesterday). "
                          f"Monitor closely for the next 2-3 days.",
                "priority": "medium",
                "type": "increasing_trend"
            })
        elif analysis.day_over_day_change < self.DECREASING_THRESHOLD:
            recommendations.append({
                "message": f"📉 Costs are decreasing ({analysis.day_over_day_change:+.0%} vs yesterday). "
                          f"Good trend to maintain!",
                "priority": "low",
                "type": "decreasing_trend"
            })
        
        # Week-over-week trend
        if abs(analysis.week_over_week_change) > Decimal("0.05"):  # >5% change
            if analysis.week_over_week_change > 0:
                recommendations.append({
                    "message": f"Week-over-week costs increased by {analysis.week_over_week_change:.0%}. "
                              f"Total: ${analysis.total_cost:.2f} for the period.",
                    "priority": "medium",
                    "type": "weekly_trend"
                })
        
        # Overall cost assessment
        if analysis.avg_daily_cost > Decimal("20.00"):
            recommendations.append({
                "message": f"💰 Daily average cost is high: ${analysis.avg_daily_cost:.2f}/day. "
                          f"Consider reviewing tier allocation for cost optimization.",
                "priority": "medium",
                "type": "high_cost"
            })
        
        # Stability recommendation
        if abs(analysis.day_over_day_change) < Decimal("0.05"):  # Within 5%
            recommendations.append({
                "message": f"✓ Costs are stable (±5% day-over-day). "
                          f"Average: ${analysis.avg_daily_cost:.2f}/day.",
                "priority": "low",
                "type": "stable"
            })
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return recommendations
    
    def get_cost_projection(self, daily_costs: List[Decimal],
                           days_ahead: int = 7) -> Dict[str, Decimal]:
        """
        Project future costs based on recent trends.
        
        Args:
            daily_costs: Recent daily costs (last 7-14 days recommended)
            days_ahead: Number of days to project
        
        Returns:
            Dictionary with projection metrics
        """
        if len(daily_costs) < 7:
            return {"error": "Insufficient data for projection"}
        
        # Use simple moving average
        recent_avg = sum(daily_costs[-7:]) / Decimal("7")
        
        # Calculate trend factor (last 3 days vs first 3 of the 7)
        first_3_avg = sum(daily_costs[-7:-4]) / Decimal("3")
        last_3_avg = sum(daily_costs[-3:]) / Decimal("3")
        
        trend_factor = last_3_avg / first_3_avg if first_3_avg > 0 else Decimal("1.00")
        
        # Project
        projected_total = recent_avg * Decimal(days_ahead) * trend_factor
        projected_daily = projected_total / Decimal(days_ahead)
        
        return {
            "days_projected": days_ahead,
            "current_avg_daily": recent_avg,
            "trend_factor": trend_factor,
            "projected_total": projected_total,
            "projected_daily_avg": projected_daily
        }
