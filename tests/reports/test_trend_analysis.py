"""
Tests for TrendAnalysis module (reports/trend_analysis.py).

These tests cover cost trend detection and analysis functionality.

P4-5: Daily Cost Reporting - Trend Analysis Tests
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from src.reports.trend_analysis import (
    TrendAnalyzer, 
    TrendAnalysis, 
    TrendAnalysis as TrendAnalysisDataclass
)


class TestTrendAnalysisDataclass:
    """Tests for the TrendAnalysis dataclass."""
    
    def test_trend_analysis_creation(self):
        """Test creating a basic TrendAnalysis object."""
        analysis = TrendAnalysis(
            period_start=date.today() - timedelta(days=6),
            period_end=date.today(),
            total_cost=Decimal("50.00"),
            task_count=100,
            avg_daily_cost=Decimal("7.14"),
            day_over_day_change=Decimal("0.10"),
            week_over_week_change=Decimal("-0.05"),
            has_spending_spike=False
        )
        
        assert analysis.total_cost == Decimal("50.00")
        assert analysis.task_count == 100
    
    def test_trend_analysis_with_spike(self):
        """Test TrendAnalysis with spending spike detected."""
        analysis = TrendAnalysis(
            period_start=date.today() - timedelta(days=6),
            period_end=date.today(),
            total_cost=Decimal("100.00"),
            task_count=50,
            avg_daily_cost=Decimal("14.29"),
            day_over_day_change=Decimal("0.75"),
            week_over_week_change=Decimal("0.30"),
            has_spending_spike=True
        )
        
        assert analysis.has_spending_spike


class TestTrendAnalyzerBasic:
    """Tests for TrendAnalyzer basic functionality."""
    
    def test_analyzer_initialization(self):
        """Test analyzer initializes with correct thresholds."""
        analyzer = TrendAnalyzer()
        
        assert analyzer.SPIKE_THRESHOLD == Decimal("0.50")
        assert analyzer.INCREASING_THRESHOLD == Decimal("0.10")


class TestTrendAnalyzer7Day:
    """Tests for 7-day trend analysis."""
    
    def test_analyze_7_day_trend_basic(self):
        """Test basic 7-day trend analysis."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("5.00") for _ in range(7)]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        assert isinstance(analysis, TrendAnalysis)
        assert analysis.total_cost == Decimal("35.00")
    
    def test_analyze_7_day_trend_with_task_counts(self):
        """Test 7-day trend analysis with task counts."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("5.00") for _ in range(7)]
        task_counts = [10, 12, 8, 15, 10, 12, 9]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs, task_counts)
        
        assert analysis.task_count == sum(task_counts)


class TestTrendAnalyzer30Day:
    """Tests for 30-day trend analysis."""
    
    def test_analyze_30_day_trend_exact(self):
        """Test 30-day trend analysis with exactly 30 days."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("5.00") for _ in range(30)]
        
        analysis = analyzer.analyze_30_day_trend(daily_costs)
        
        assert analysis.total_cost == Decimal("150.00")


class TestDayOverDayChangeCalculation:
    """Tests for day-over-day change calculation methods."""
    
    def test_calculate_extended_day_over_day_change_increasing(self):
        """Test extended DoD change with increasing costs."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("5.00"), Decimal("10.00")]
        
        change = analyzer._calculate_extended_day_over_day_change(daily_costs)
        
        assert change == Decimal("1.00")


class TestWeekOverWeekChangeCalculation:
    """Tests for week-over-week change calculation."""
    
    def test_calculate_week_over_week_increase(self):
        """Test week-over-week with increase."""
        analyzer = TrendAnalyzer()
        
        change = analyzer._calculate_week_over_week_change(Decimal("50.00"), Decimal("60.00"))
        
        assert change == Decimal("0.20")


class TestTierTrendAnalysis:
    """Tests for tier-specific trend analysis."""
    
    def test_analyze_tier_trends_single_tier(self):
        """Test tier trend analysis with single tier."""
        analyzer = TrendAnalyzer()
        
        tier_costs = {"L0": [Decimal("2.00") for _ in range(7)]}
        
        results = analyzer.analyze_tier_trends(tier_costs)
        
        assert "L0" in results


class TestTrendRecommendations:
    """Tests for trend-based recommendations."""
    
    def test_generate_recommendations_spike_alert(self):
        """Test recommendations include spike alert when detected."""
        analyzer = TrendAnalyzer()
        
        analysis = TrendAnalysis(
            period_start=date.today() - timedelta(days=6),
            period_end=date.today(),
            total_cost=Decimal("100.00"),
            task_count=50,
            avg_daily_cost=Decimal("14.29"),
            day_over_day_change=Decimal("0.75"),
            week_over_week_change=Decimal("0.30"),
            has_spending_spike=True
        )
        
        recommendations = analyzer.generate_trend_recommendations(analysis)
        
        spike_alerts = [r for r in recommendations if r["type"] == "spike_alert"]
        assert len(spike_alerts) > 0


class TestCostProjection:
    """Tests for cost projection functionality."""
    
    def test_get_cost_projection_7_days(self):
        """Test cost projection with 7 days of data."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("5.00") for _ in range(14)]
        
        projection = analyzer.get_cost_projection(daily_costs, days_ahead=7)
        
        assert "projected_total" in projection


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_zero_values_handling(self):
        """Test handling of zero values in cost data."""
        analyzer = TrendAnalyzer()
        
        daily_costs = [Decimal("0.00"), Decimal("5.00")]
        
        analysis = analyzer.analyze_7_day_trend(daily_costs)
        
        assert analysis.total_cost == Decimal("5.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
