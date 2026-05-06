"""
Phase 3 Analytics Tools Tests

Tests for analytics functionality including summary generation, tier breakdown,
cost trends analysis, and efficiency reporting.

Test Coverage:
- Analytics service methods
- Request/response processing
- Mock data generation
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp.analytics_tools import (
    AnalyticsService,
    MockDataGenerator,
    process_analytics_summary,
    process_tier_breakdown,
    process_cost_trends,
    process_efficiency_report,
    AnalyticsSummaryRequest,
    TierBreakdownRequest,
    CostTrendsRequest,
    EfficiencyReportRequest,
)


class TestAnalyticsService:
    """Test analytics service functionality."""
    
    def test_generate_summary(self):
        """Test generating overall summary."""
        service = AnalyticsService()
        
        result = service.generate_summary(period_days=7)
        
        assert "period" in result
        assert "total_spent" in result
        assert "task_count" in result
        assert "avg_cost_per_task" in result
        assert "tier_distribution" in result
        assert result["period"] == "7 days"
        assert isinstance(result["total_spent"], (int, float))
        assert result["total_spent"] > 0
    
    def test_generate_summary_custom_period(self):
        """Test generating summary with custom period."""
        service = AnalyticsService()
        
        result = service.generate_summary(period_days=30)
        
        assert result["period"] == "30 days"
    
    def test_generate_tier_breakdown(self):
        """Test generating tier breakdown."""
        service = AnalyticsService()
        
        result = service.generate_tier_breakdown(period_days=7)
        
        assert "period" in result
        assert "tiers" in result
        assert "L0" in result["tiers"]
        assert "L1" in result["tiers"]
        assert "L2" in result["tiers"]
        assert "L3" in result["tiers"]
        assert "most_used_tier" in result
        assert "highest_cost_tier" in result
    
    def test_tier_breakdown_data_structure(self):
        """Test tier breakdown data structure."""
        service = AnalyticsService()
        
        result = service.generate_tier_breakdown(period_days=7)
        
        for tier_name, tier_data in result["tiers"].items():
            assert "task_count" in tier_data
            assert "total_cost" in tier_data
            assert "avg_cost_per_task" in tier_data
            assert "percentage_of_total" in tier_data
    
    def test_generate_cost_trends(self):
        """Test generating cost trends."""
        service = AnalyticsService()
        
        result = service.generate_cost_trends(period_days=7)
        
        assert "period" in result
        assert "trend_direction" in result
        assert "change_percent" in result
        assert "daily_data" in result
        assert "ascii_chart" in result
        assert isinstance(result["daily_data"], list)
        assert len(result["daily_data"]) == 7
    
    def test_cost_trend_directions(self):
        """Test different trend directions."""
        service = AnalyticsService()
        
        # Test with different periods to get different trends
        for days in [3, 7, 14]:
            result = service.generate_cost_trends(period_days=days)
            
            assert result["trend_direction"] in [
                "increasing", "decreasing", "stable", "insufficient_data"
            ]
            assert isinstance(result["change_percent"], (int, float))
    
    def test_generate_efficiency_report(self):
        """Test generating efficiency report."""
        service = AnalyticsService()
        
        result = service.generate_efficiency_report(period_days=7)
        
        assert "period" in result
        assert "overall_efficiency_score" in result
        assert "tier_analysis" in result
        assert "optimization_suggestions" in result
    
    def test_efficiency_report_structure(self):
        """Test efficiency report data structure."""
        service = AnalyticsService()
        
        result = service.generate_efficiency_report(period_days=7)
        
        assert isinstance(result["overall_efficiency_score"], int)
        assert 0 <= result["overall_efficiency_score"] <= 100
        assert isinstance(result["optimization_suggestions"], list)
        assert len(result["optimization_suggestions"]) > 0


class TestMockDataGenerator:
    """Test mock data generation."""
    
    def test_generate_summary_data(self):
        """Test generating summary mock data."""
        generator = MockDataGenerator()
        
        data = generator.generate_summary_data(period_days=7)
        
        assert "total_cost" in data
        assert "task_count" in data
        assert "avg_cost_per_task" in data
        assert data["total_cost"] > 0
        assert data["task_count"] > 0
    
    def test_generate_tier_breakdown_data(self):
        """Test generating tier breakdown mock data."""
        generator = MockDataGenerator()
        
        data = generator.generate_tier_breakdown(period_days=7)
        
        assert "L0" in data
        assert "L1" in data
        assert "L2" in data
        assert "L3" in data
        
        for tier_name, stats in data.items():
            assert "count" in stats
            assert "cost" in stats
            assert "avg_cost" in stats
    
    def test_generate_trends_data(self):
        """Test generating trends mock data."""
        generator = MockDataGenerator()
        
        trends = generator.generate_trends(period_days=7)
        
        assert isinstance(trends, list)
        assert len(trends) == 7
        
        for trend in trends:
            assert hasattr(trend, 'date')
            assert hasattr(trend, 'total_cost')
            assert hasattr(trend, 'task_count')


class TestProcessingFunctions:
    """Test request/response processing functions."""
    
    def test_process_analytics_summary_success(self):
        """Test successful analytics summary processing."""
        request = AnalyticsSummaryRequest(
            session_id="test-session",
            period_days=7,
            include_breakdown=True
        )
        
        response = process_analytics_summary(request)
        
        assert response.success is True
        assert response.data is not None
        assert "total_spent" in response.data
    
    def test_process_tier_breakdown_success(self):
        """Test successful tier breakdown processing."""
        request = TierBreakdownRequest(
            session_id="test-session",
            period_days=7
        )
        
        response = process_tier_breakdown(request)
        
        assert response.success is True
        assert response.data is not None
        assert "tiers" in response.data
    
    def test_process_cost_trends_success(self):
        """Test successful cost trends processing."""
        request = CostTrendsRequest(
            session_id="test-session",
            period_days=7
        )
        
        response = process_cost_trends(request)
        
        assert response.success is True
        assert response.data is not None
        assert "trend_direction" in response.data
    
    def test_process_efficiency_report_success(self):
        """Test successful efficiency report processing."""
        request = EfficiencyReportRequest(
            session_id="test-session",
            period_days=7
        )
        
        response = process_efficiency_report(request)
        
        assert response.success is True
        assert response.data is not None
        assert "overall_efficiency_score" in response.data
    
    def test_process_without_session_id(self):
        """Test processing without session ID."""
        request = AnalyticsSummaryRequest(period_days=7)
        
        response = process_analytics_summary(request)
        
        assert response.success is True
        assert response.data is not None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_min_period_days(self):
        """Test minimum period (1 day)."""
        request = CostTrendsRequest(period_days=1)
        
        response = process_cost_trends(request)
        
        assert response.success is True
    
    def test_max_period_days(self):
        """Test maximum period (365 days)."""
        request = AnalyticsSummaryRequest(period_days=365)
        
        response = process_analytics_summary(request)
        
        assert response.success is True
    
    def test_unicode_in_session_id(self):
        """Test session ID with unicode characters."""
        request = TierBreakdownRequest(
            session_id="session-测试",
            period_days=7
        )
        
        response = process_tier_breakdown(request)
        
        assert response.success is True
    
    def test_very_long_session_id(self):
        """Test very long session ID."""
        long_session_id = "session-" + "a" * 1000
        
        request = EfficiencyReportRequest(
            session_id=long_session_id,
            period_days=7
        )
        
        response = process_efficiency_report(request)
        
        # Should not fail even with long session ID
        assert response.success is True or response.error is not None


class TestResponseValidation:
    """Test response data validation."""
    
    def test_analytics_summary_all_fields_present(self):
        """Test all expected fields present in analytics summary."""
        request = AnalyticsSummaryRequest(period_days=7)
        
        response = process_analytics_summary(request)
        
        assert response.success is True
        
        required_fields = [
            "period",
            "total_spent",
            "task_count", 
            "avg_cost_per_task",
            "tier_distribution",
            "trend_direction",
            "efficiency_score"
        ]
        
        for field in required_fields:
            assert field in response.data, f"Missing field: {field}"
    
    def test_tier_breakdown_all_tiers_present(self):
        """Test all tiers present in breakdown."""
        request = TierBreakdownRequest(period_days=7)
        
        response = process_tier_breakdown(request)
        
        assert response.success is True
        
        expected_tiers = ["L0", "L1", "L2", "L3"]
        for tier in expected_tiers:
            assert tier in response.data["tiers"], f"Missing tier: {tier}"
    
    def test_cost_trends_daily_data_structure(self):
        """Test daily data structure in trends."""
        request = CostTrendsRequest(period_days=7)
        
        response = process_cost_trends(request)
        
        assert response.success is True
        assert len(response.data["daily_data"]) == 7
        
        for day_data in response.data["daily_data"]:
            assert "date" in day_data
            assert "total_cost" in day_data
            assert "task_count" in day_data
    
    def test_efficiency_score_range(self):
        """Test efficiency score is within valid range."""
        request = EfficiencyReportRequest(period_days=7)
        
        response = process_efficiency_report(request)
        
        assert response.success is True
        assert 0 <= response.data["overall_efficiency_score"] <= 100
    
    def test_tier_efficiency_scores(self):
        """Test all tier efficiency scores are valid."""
        request = TierBreakdownRequest(period_days=7)
        
        response = process_tier_breakdown(request)
        
        assert response.success is True
        
        for tier_name, tier_data in response.data["tiers"].items():
            if "efficiency_score" in tier_data:
                assert 0 <= tier_data["efficiency_score"] <= 100


class TestIntegrationWorkflows:
    """Test complete workflow scenarios."""
    
    def test_analytics_workflow_sequence(self):
        """Test typical analytics workflow sequence."""
        # Step 1: Get summary
        summary_request = AnalyticsSummaryRequest(period_days=7)
        summary_response = process_analytics_summary(summary_request)
        
        assert summary_response.success is True
        
        # Step 2: Get tier breakdown
        breakdown_request = TierBreakdownRequest(period_days=7)
        breakdown_response = process_tier_breakdown(breakdown_request)
        
        assert breakdown_response.success is True
        
        # Step 3: Get trends
        trends_request = CostTrendsRequest(period_days=7)
        trends_response = process_cost_trends(trends_request)
        
        assert trends_response.success is True
        
        # Step 4: Get efficiency report
        efficiency_request = EfficiencyReportRequest(period_days=7)
        efficiency_response = process_efficiency_report(efficiency_request)
        
        assert efficiency_response.success is True
        
        # Verify all responses have data
        assert summary_response.data is not None
        assert breakdown_response.data is not None
        assert trends_response.data is not None
        assert efficiency_response.data is not None
    
    def test_different_periods_workflow(self):
        """Test analytics with different time periods."""
        periods = [1, 7, 14, 30]
        
        for days in periods:
            request = AnalyticsSummaryRequest(period_days=days)
            response = process_analytics_summary(request)
            
            assert response.success is True
            assert response.data["period"] == f"{days} days"
    
    def test_consistent_data_across_tools(self):
        """Test data consistency across different analytics tools."""
        summary_request = AnalyticsSummaryRequest(period_days=7)
        summary_response = process_analytics_summary(summary_request)
        
        breakdown_request = TierBreakdownRequest(period_days=7)
        breakdown_response = process_tier_breakdown(breakdown_request)
        
        # Both should use same period
        assert summary_response.data["period"] == breakdown_response.data["period"]


class TestASCIIChartGeneration:
    """Test ASCII chart generation."""
    
    def test_ascii_chart_generated(self):
        """Test that ASCII chart is generated."""
        request = CostTrendsRequest(period_days=7)
        
        response = process_cost_trends(request)
        
        assert response.success is True
        assert "ascii_chart" in response.data
        assert len(response.data["ascii_chart"]) > 0
    
    def test_ascii_chart_contains_visual_elements(self):
        """Test ASCII chart contains visual elements."""
        request = CostTrendsRequest(period_days=7)
        
        response = process_cost_trends(request)
        
        chart = response.data["ascii_chart"]
        
        # Should contain some characters indicating a chart
        assert isinstance(chart, str)
        assert len(chart) > 10


class TestOptimizationSuggestions:
    """Test optimization suggestions generation."""
    
    def test_suggestions_generated(self):
        """Test that optimization suggestions are generated."""
        request = EfficiencyReportRequest(period_days=7)
        
        response = process_efficiency_report(request)
        
        assert response.success is True
        assert "optimization_suggestions" in response.data
        assert isinstance(response.data["optimization_suggestions"], list)
        assert len(response.data["optimization_suggestions"]) > 0
    
    def test_suggestions_are_actionable(self):
        """Test that suggestions contain actionable information."""
        request = EfficiencyReportRequest(period_days=7)
        
        response = process_efficiency_report(request)
        
        suggestions = response.data["optimization_suggestions"]
        
        # Each suggestion should be a meaningful string
        for suggestion in suggestions:
            assert isinstance(suggestion, str)
            assert len(suggestion) > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
