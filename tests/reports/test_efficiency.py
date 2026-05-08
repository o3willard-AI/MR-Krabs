"""
Tests for Efficiency Analysis module (reports/efficiency.py).

These tests cover efficiency analysis and tier performance evaluation.

P4-5: Daily Cost Reporting - Efficiency Analysis Tests
"""

import pytest
from decimal import Decimal
from src.reports.efficiency import TierEfficiencyAnalysis, TierEfficiencyAnalyzer


class TestTierEfficiencyAnalysisDataclass:
    """Tests for the TierEfficiencyAnalysis dataclass."""
    
    def test_tier_efficiency_analysis_creation(self):
        """Test creating a basic TierEfficiencyAnalysis object."""
        analysis = TierEfficiencyAnalysis(
            tier_name="L0",
            usage_count=100,
            total_cost=Decimal("50.00"),
            avg_cost_per_task=Decimal("0.50"),
            success_rate=Decimal("0.95"),
            efficiency_score=85
        )
        
        assert analysis.tier_name == "L0"
        assert analysis.usage_count == 100
        assert analysis.total_cost == Decimal("50.00")
        assert analysis.efficiency_score == 85
    
    def test_tier_efficiency_analysis_zero_usage(self):
        """Test TierEfficiencyAnalysis with zero usage."""
        analysis = TierEfficiencyAnalysis(
            tier_name="L3",
            usage_count=0,
            total_cost=Decimal("0.00"),
            avg_cost_per_task=Decimal("0.00"),
            success_rate=Decimal("0.00"),
            efficiency_score=0
        )
        
        assert analysis.usage_count == 0
        assert analysis.efficiency_score == 0


class TestTierEfficiencyAnalyzer:
    """Tests for the TierEfficiencyAnalyzer class."""
    
    def test_analyzer_initialization(self):
        """Test analyzer initializes with correct thresholds."""
        analyzer = TierEfficiencyAnalyzer()
        
        assert analyzer.LOW_COST_THRESHOLD == Decimal("0.10")
        assert analyzer.HIGH_COST_THRESHOLD == Decimal("1.00")
        assert analyzer.EXCELLENT_SUCCESS_RATE == Decimal("0.98")
        assert analyzer.MINIMUM_SUCCESS_RATE == Decimal("0.80")
    
    def test_analyze_tier_efficiency_basic(self):
        """Test basic tier efficiency calculation."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 100,
            "cost": Decimal("50.00"),
            "success_count": 95
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L0")
        
        assert isinstance(analysis, TierEfficiencyAnalysis)
        assert analysis.tier_name == "L0"
        assert analysis.avg_cost_per_task == Decimal("0.50")
        assert analysis.success_rate == Decimal("0.95")
    
    def test_analyze_tier_efficiency_zero_count(self):
        """Test tier efficiency with zero task count."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 0,
            "cost": Decimal("0.00"),
            "success_count": 0
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L1")
        
        assert analysis.usage_count == 0
        assert analysis.avg_cost_per_task == Decimal("0.00")
    
    def test_analyze_tier_efficiency_all_failed(self):
        """Test tier efficiency when all tasks failed."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 50,
            "cost": Decimal("100.00"),
            "success_count": 0
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L2")
        
        assert analysis.success_rate == Decimal("0.00")
    
    def test_analyze_tier_efficiency_all_success(self):
        """Test tier efficiency when all tasks succeeded."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 50,
            "cost": Decimal("25.00"),
            "success_count": 50
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L0")
        
        assert analysis.success_rate == Decimal("1.00")


class TestEfficiencyScoreCalculation:
    """Tests for efficiency score calculation."""
    
    def test_efficiency_score_low_cost_high_success(self):
        """Test efficiency score with low cost and high success rate."""
        analyzer = TierEfficiencyAnalyzer()
        
        analysis = analyzer.analyze_tier_efficiency(
            {"count": 100, "cost": Decimal("5.00"), "success_count": 98},
            tier_name="L0"
        )
        
        # Low cost + high success should give high score
        assert analysis.efficiency_score >= 70
    
    def test_efficiency_score_high_cost_low_success(self):
        """Test efficiency score with high cost and low success rate."""
        analyzer = TierEfficiencyAnalyzer()
        
        analysis = analyzer.analyze_tier_efficiency(
            {"count": 50, "cost": Decimal("100.00"), "success_count": 30},
            tier_name="L3"
        )
        
        # High cost + low success should give low score
        assert analysis.efficiency_score < 50
    
    def test_efficiency_score_mixed(self):
        """Test efficiency score with mixed metrics."""
        analyzer = TierEfficiencyAnalyzer()
        
        analysis = analyzer.analyze_tier_efficiency(
            {"count": 100, "cost": Decimal("50.00"), "success_count": 85},
            tier_name="L1"
        )
        
        # Should be in middle range
        assert 40 <= analysis.efficiency_score <= 90


class TestAnalyzeAllTiers:
    """Tests for analyzing all tiers at once."""
    
    def test_analyze_all_tiers_basic(self):
        """Test analyzing multiple tiers."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 100, "cost": Decimal("50.00"), "success_count": 95},
            "L1": {"count": 50, "cost": Decimal("75.00"), "success_count": 48},
            "L2": {"count": 25, "cost": Decimal("100.00"), "success_count": 23}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        
        assert len(analyses) == 3
        assert all(isinstance(a, TierEfficiencyAnalysis) for a in analyses)
    
    def test_analyze_all_tiers_empty(self):
        """Test analyzing empty tier data."""
        analyzer = TierEfficiencyAnalyzer()
        
        analyses = analyzer.analyze_all_tiers({})
        
        assert len(analyses) == 0


class TestOptimizationSuggestions:
    """Tests for optimization suggestion generation."""
    
    def test_get_optimization_suggestions_basic(self):
        """Test generating basic suggestions."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 100, "cost": Decimal("50.00"), "success_count": 95},
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        assert isinstance(suggestions, list)
    
    def test_get_optimization_suggestions_overused(self):
        """Test suggestions include overuse warning."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 90, "cost": Decimal("45.00"), "success_count": 85},
            "L1": {"count": 5, "cost": Decimal("10.00"), "success_count": 5},
            "L2": {"count": 5, "cost": Decimal("20.00"), "success_count": 4}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        # Should have overuse suggestion for L0
        overuse_suggestions = [s for s in suggestions if s["type"] == "overuse"]
        assert len(overuse_suggestions) >= 1
    
    def test_get_optimization_suggestions_high_cost(self):
        """Test suggestions include high cost warning."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L3": {"count": 20, "cost": Decimal("50.00"), "success_count": 15}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        high_cost_suggestions = [s for s in suggestions if s["type"] == "cost"]
        assert len(high_cost_suggestions) >= 1
    
    def test_get_optimization_suggestions_priority_ordering(self):
        """Test suggestions are sorted by priority."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L3": {"count": 50, "cost": Decimal("200.00"), "success_count": 20}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        if len(suggestions) > 1:
            # First should be high priority
            assert suggestions[0]["priority"] == "high"


class TestIdentifyOverusedTiers:
    """Tests for identifying overused tiers."""
    
    def test_identify_overused_tiers(self):
        """Test identification of overused tiers."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 95, "cost": Decimal("47.50"), "success_count": 90},
            "L1": {"count": 3, "cost": Decimal("6.00"), "success_count": 3},
            "L2": {"count": 2, "cost": Decimal("8.00"), "success_count": 2}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        overused = analyzer.identify_overused_tiers(analyses)
        
        assert len(overused) >= 1
        assert overused[0].tier_name == "L0"
    
    def test_identify_overused_tiers_none(self):
        """Test no overused tiers when distribution is even."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 33, "cost": Decimal("16.50"), "success_count": 30},
            "L1": {"count": 33, "cost": Decimal("49.50"), "success_count": 30},
            "L2": {"count": 34, "cost": Decimal("136.00"), "success_count": 30}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        overused = analyzer.identify_overused_tiers(analyses)
        
        assert len(overused) == 0


class TestIdentifyUnderusedTiers:
    """Tests for identifying underused tiers."""
    
    def test_identify_underused_tiers(self):
        """Test identification of underused tiers."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 100, "cost": Decimal("50.00"), "success_count": 95},
            "L3": {"count": 1, "cost": Decimal("5.00"), "success_count": 1}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        underused = analyzer.identify_underused_tiers(analyses)
        
        assert len(underused) >= 1


class TestRankByEfficiency:
    """Tests for tier ranking by efficiency."""
    
    def test_rank_by_efficiency(self):
        """Test ranking tiers by efficiency score."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 100, "cost": Decimal("10.00"), "success_count": 98},
            "L1": {"count": 50, "cost": Decimal("100.00"), "success_count": 40},
            "L2": {"count": 25, "cost": Decimal("200.00"), "success_count": 15}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        ranked = analyzer.rank_by_efficiency(analyses)
        
        # L0 should be first (most efficient)
        assert ranked[0].tier_name == "L0"


class TestSummaryReport:
    """Tests for summary report generation."""
    
    def test_get_summary_report(self):
        """Test generating summary report."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 100, "cost": Decimal("50.00"), "success_count": 95},
            "L1": {"count": 50, "cost": Decimal("75.00"), "success_count": 48}
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        summary = analyzer.get_summary_report(analyses)
        
        assert "total_cost" in summary
        assert "total_tasks" in summary
        assert "best_tier" in summary
        assert "worst_tier" in summary
    
    def test_get_summary_report_empty(self):
        """Test summary report with no analyses."""
        analyzer = TierEfficiencyAnalyzer()
        
        summary = analyzer.get_summary_report([])
        
        assert "error" in summary


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_zero_costs(self):
        """Test handling of zero costs."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0": {"count": 10, "cost": Decimal("0.00"), "success_count": 10}
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L0")
        
        assert analysis.total_cost == Decimal("0.00")
        assert analysis.avg_cost_per_task == Decimal("0.00")
    
    def test_very_high_success_rate(self):
        """Test handling of 100% success rate."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 100,
            "cost": Decimal("50.00"),
            "success_count": 100  # 100% success
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, tier_name="L0")
        
        assert analysis.success_rate == Decimal("1.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
