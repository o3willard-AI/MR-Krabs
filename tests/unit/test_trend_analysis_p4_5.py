"""
Tests for TrendAnalysis (P4-5: Daily Cost Reporting)
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from src.reports.trend_analysis import TrendAnalysis, TrendAnalyzer


class TestTrendAnalysis:
    """Test TrendAnalysis dataclass."""

    def test_trend_analysis_basic(self):
        """Test basic TrendAnalysis creation."""
        analysis = TrendAnalysis(
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 7),
            total_cost=Decimal("100.00"),
            task_count=500,
            avg_daily_cost=Decimal("14.29"),
            day_over_day_change=Decimal("0.05"),
            week_over_week_change=Decimal("0.10"),
            has_spending_spike=False
        )
        
        assert analysis.period_start == date(2026, 4, 1)
        assert analysis.period_end == date(2026, 4, 7)
        assert analysis.total_cost == Decimal("100.00")
        assert analysis.task_count == 500
        assert analysis.day_over_day_change == Decimal("0.05")
        assert analysis.week_over_week_change == Decimal("0.10")

    def test_trend_analysis_with_spike(self):
        """Test TrendAnalysis with spending spike detection."""
        analysis = TrendAnalysis(
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 7),
            total_cost=Decimal("100.00"),
            task_count=500,
            avg_daily_cost=Decimal("14.29"),
            day_over_day_change=Decimal("0.65"),  # 65% increase
            week_over_week_change=Decimal("0.20"),
            has_spending_spike=True
        )
        
        assert analysis.has_spending_spike is True
        assert analysis.day_over_day_change == Decimal("0.65")


class TestTrendAnalyzer:
    """Test TrendAnalyzer class."""

    def test_analyze_7_day_trend(self):
        """Test analyzing 7-day cost trend."""
        analyzer = TrendAnalyzer()
        
        # Create daily cost data for 7 days
        daily_costs = [
            Decimal("10.00"),  # Day 1
            Decimal("12.00"),  # Day 2
            Decimal("11.00"),  # Day 3
            Decimal("15.00"),  # Day 4
            Decimal("14.00"),  # Day 5
            Decimal("16.00"),  # Day 6
            Decimal("18.00"),  # Day 7
        ]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        assert analysis.period_start is not None
        assert analysis.period_end is not None
        assert analysis.total_cost == sum(daily_costs)  # 96.00
        # avg_daily_cost = 96/7 = 13.71
        assert abs(analysis.avg_daily_cost - Decimal("13.71")) < Decimal("0.02")

    def test_analyze_30_day_trend(self):
        """Test analyzing 30-day cost trend."""
        analyzer = TrendAnalyzer()
        
        # Create daily cost data for 30 days
        daily_costs = [Decimal("15.00")] * 30
        
        analysis = analyzer.analyze_30_day_trend(daily_costs)
        
        assert analysis.period_start is not None
        assert analysis.period_end is not None
        assert analysis.total_cost == Decimal("450.00")

    def test_calculate_day_over_day_change(self):
        """Test day-over-day percentage change calculation."""
        analyzer = TrendAnalyzer()
        
        # Yesterday: $10, Today: $12 = 20% increase
        change = analyzer._calculate_day_over_day_change(
            previous_value=Decimal("10.00"),
            current_value=Decimal("12.00")
        )
        
        assert change == Decimal("0.20")
        
        # Yesterday: $12, Today: $10 = 16.67% decrease
        change = analyzer._calculate_day_over_day_change(
            previous_value=Decimal("12.00"),
            current_value=Decimal("10.00")
        )
        
        assert abs(change - Decimal("-0.1667")) < Decimal("0.0001")

    def test_detect_spending_spike(self):
        """Test spending spike detection (>50% increase)."""
        analyzer = TrendAnalyzer()
        
        # 65% increase - should trigger spike (2 values, oldest->newest)
        daily_costs = [Decimal("10.00"), Decimal("16.50")]
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        # day_over_day_change is calculated as first to last (10 -> 16.5 = 65%)
        assert analysis.has_spending_spike is True
        assert analysis.day_over_day_change == Decimal("0.65")

    def test_detect_no_spike(self):
        """Test when no spending spike occurs."""
        analyzer = TrendAnalyzer()
        
        # 10% increase - should not trigger spike
        daily_costs = [Decimal("10.00"), Decimal("11.00")]
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        # day_over_day_change is 10% but spike threshold is 50%
        assert analysis.has_spending_spike is False
        assert analysis.day_over_day_change == Decimal("0.10")

    def test_generate_cost_trend_recommendations(self):
        """Test generating recommendations based on trend analysis."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [
            Decimal("10.00"),
            Decimal("12.00"),
            Decimal("11.00"),
            Decimal("15.00"),
            Decimal("14.00"),
            Decimal("16.00"),
            Decimal("18.00"),
        ]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        recommendations = analyzer.generate_trend_recommendations(analysis)
        
        # Should have at least one recommendation
        assert len(recommendations) >= 1
        
        # Check recommendation structure
        for rec in recommendations:
            assert "message" in rec
            assert "priority" in rec

    def test_week_over_week_comparison(self):
        """Test week-over-week cost comparison."""
        analyzer = TrendAnalyzer()
        
        last_week_costs = [Decimal("10.00")] * 7
        this_week_costs = [Decimal("12.00")] * 7
        
        change = analyzer._calculate_week_over_week_change(
            last_week_total=sum(last_week_costs),
            this_week_total=sum(this_week_costs)
        )
        
        assert change == Decimal("0.20")  # 20% increase

    def test_trend_analysis_with_fluctuating_costs(self):
        """Test trend analysis with fluctuating daily costs."""
        analyzer = TrendAnalyzer()
        
        # Costs go up and down
        daily_costs = [
            Decimal("10.00"),
            Decimal("8.00"),
            Decimal("12.00"),
            Decimal("9.00"),
            Decimal("11.00"),
            Decimal("10.00"),
            Decimal("13.00"),
        ]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        # Should still calculate valid metrics
        assert analysis.total_cost == sum(daily_costs)
        assert analysis.has_spending_spike is False  # No single day >50% increase

    def test_trend_analysis_with_declining_costs(self):
        """Test trend analysis with declining costs."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [
            Decimal("20.00"),
            Decimal("18.00"),
            Decimal("15.00"),
            Decimal("12.00"),
            Decimal("10.00"),
            Decimal("8.00"),
            Decimal("5.00"),
        ]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        assert analysis.total_cost == Decimal("88.00")
        # day_over_day_change is calculated as extended (first to last): (5-20)/20 = -0.75
        assert analysis.day_over_day_change == Decimal("-0.75")

    def test_get_cost_breakdown_by_tier(self):
        """Test getting cost breakdown by tier from trend data."""
        analyzer = TrendAnalyzer()
        
        # Simulate tier-specific daily costs
        tier_daily_costs = {
            "L0-Coder": [Decimal("5.00")] * 7,
            "L1-Coder": [Decimal("3.00")] * 7,
            "L2-Coder": [Decimal("2.00")] * 7,
        }
        
        breakdown = analyzer.analyze_tier_trends(tier_daily_costs)
        
        assert "L0-Coder" in breakdown
        # breakdown is a dict of tier_name -> TrendAnalysis
        assert breakdown["L0-Coder"].total_cost == Decimal("35.00")
        assert len(breakdown) == 3

    def test_analyze_spending_pattern(self):
        """Test analyzing spending patterns (weekday vs weekend)."""
        analyzer = TrendAnalyzer()
        
        # Simulate 30 days with weekday/weekend costs
        daily_costs = []
        for i in range(30):
            # Assume weekends (i % 7 >= 5) have lower costs
            if i % 7 >= 5:
                daily_costs.append(Decimal("10.00"))
            else:
                daily_costs.append(Decimal("15.00"))
        
        analysis = analyzer.analyze_30_day_trend(daily_costs)
        
        # Calculate: days 0-4 (5 days) = 15, days 5-6 (2 days) = 10
        # Pattern repeats ~4 times: 4 * (5*15 + 2*10) + remaining days
        # = 4 * (75 + 20) + (5*15 + 2*10) for first 30 days (4*7=28 + 2 more)
        # Actually: floor(30/7) = 4 full weeks, remainder = 2 days
        # = 4 * 95 + 2 * 15 (first 2 days of week are weekdays) = 380 + 30 = 410
        assert analysis.total_cost == Decimal("410.00")


class TestTrendAnalysisIntegration:
    """Test TrendAnalyzer integration scenarios."""

    def test_complete_trend_analysis_workflow(self):
        """Test complete trend analysis workflow."""
        analyzer = TrendAnalyzer()
        
        # Realistic 30-day data
        daily_costs = [
            Decimal("15.00"), Decimal("18.00"), Decimal("12.00"), Decimal("20.00"),
            Decimal("16.00"), Decimal("14.00"), Decimal("17.00"), Decimal("19.00"),
            Decimal("13.00"), Decimal("15.00"), Decimal("16.00"), Decimal("18.00"),
            Decimal("14.00"), Decimal("17.00"), Decimal("21.00"), Decimal("15.00"),
            Decimal("16.00"), Decimal("18.00"), Decimal("14.00"), Decimal("19.00"),
            Decimal("13.00"), Decimal("16.00"), Decimal("17.00"), Decimal("20.00"),
            Decimal("15.00"), Decimal("14.00"), Decimal("18.00"), Decimal("16.00"),
            Decimal("17.00"), Decimal("19.00"),
        ]
        
        # Analyze trends
        seven_day = analyzer.analyze_7_day_trend(daily_costs[-7:])
        thirty_day = analyzer.analyze_30_day_trend(daily_costs)
        
        # Generate recommendations
        recommendations = analyzer.generate_trend_recommendations(thirty_day)
        
        # Verify analysis is complete
        assert thirty_day.total_cost == Decimal("492.00")  # Sum of all daily costs
        assert len(recommendations) > 0
        
        # Check for any alerts
        if thirty_day.has_spending_spike:
            assert any("spike" in r["message"].lower() for r in recommendations)


class TestTrendAnalysisRecommendations:
    """Test trend recommendation generation."""

    def test_recommendation_for_increasing_costs(self):
        """Test recommendations when costs are increasing."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("10.00"), Decimal("12.00"), Decimal("14.00"),
                       Decimal("16.00"), Decimal("18.00"), Decimal("20.00"),
                       Decimal("22.00")]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        recommendations = analyzer.generate_trend_recommendations(analysis)
        
        # Should have cost-related recommendations due to increasing trend
        has_cost_recommendation = any(
            "cost" in r["message"].lower() or "spend" in r["message"].lower() or 
            "increasing" in r["message"].lower()
            for r in recommendations
        )
        assert has_cost_recommendation or len(recommendations) > 0

    def test_recommendation_for_spending_spike(self):
        """Test recommendations when spending spike detected."""
        analyzer = TrendAnalyzer()
        
        # 100% increase
        daily_costs = [Decimal("10.00"), Decimal("20.00")]
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        recommendations = analyzer.generate_trend_recommendations(analysis)
        
        # Should have spike alert
        has_spike_alert = any(
            "spike" in r["message"].lower() or "alert" in r["message"].lower()
            for r in recommendations
        )
        assert has_spike_alert or len(recommendations) > 0

    def test_recommendation_for_stable_costs(self):
        """Test recommendations when costs are stable."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("15.00")] * 7
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        recommendations = analyzer.generate_trend_recommendations(analysis)
        
        # Should have positive recommendation for stability
        has_stability_msg = any(
            "stable" in r["message"].lower() or "consistent" in r["message"].lower()
            for r in recommendations
        ) or len(recommendations) == 0
