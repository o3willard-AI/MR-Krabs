"""
Tests for TierEfficiencyAnalysis (P4-5: Daily Cost Reporting)
"""

import pytest
from decimal import Decimal

from src.reports.efficiency import TierEfficiencyAnalysis, TierEfficiencyAnalyzer


class TestTierEfficiencyAnalysis:
    """Test TierEfficiencyAnalysis dataclass."""

    def test_tier_efficiency_analysis_basic(self):
        """Test basic TierEfficiencyAnalysis creation."""
        analysis = TierEfficiencyAnalysis(
            tier_name="L0-Coder",
            usage_count=100,
            total_cost=Decimal("2.50"),
            avg_cost_per_task=Decimal("0.025"),
            success_rate=Decimal("0.95"),
            efficiency_score=85
        )
        
        assert analysis.tier_name == "L0-Coder"
        assert analysis.usage_count == 100
        assert analysis.total_cost == Decimal("2.50")
        assert analysis.avg_cost_per_task == Decimal("0.025")
        assert analysis.success_rate == Decimal("0.95")
        assert analysis.efficiency_score == 85

    def test_tier_efficiency_analysis_zero_usage(self):
        """Test TierEfficiencyAnalysis with zero usage."""
        analysis = TierEfficiencyAnalysis(
            tier_name="L3-Coder",
            usage_count=0,
            total_cost=Decimal("0.00"),
            avg_cost_per_task=Decimal("0.00"),
            success_rate=Decimal("0.00"),
            efficiency_score=0
        )
        
        assert analysis.tier_name == "L3-Coder"
        assert analysis.usage_count == 0
        assert analysis.avg_cost_per_task == Decimal("0.00")


class TestTierEfficiencyAnalyzer:
    """Test TierEfficiencyAnalyzer class."""

    def test_analyze_tier_efficiency_high_usage_low_cost(self):
        """Test analyzing tier with high usage and low cost (efficient)."""
        analyzer = TierEfficiencyAnalyzer()
        
        # Simulate tier data
        tier_data = {
            "count": 500,
            "cost": Decimal("12.50"),
            "success_count": 480,
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, "L0-Coder")
        
        assert analysis.tier_name == "L0-Coder"
        assert analysis.usage_count == 500
        assert analysis.total_cost == Decimal("12.50")
        assert analysis.avg_cost_per_task == Decimal("0.025")
        assert analysis.success_rate == Decimal("0.96")
        assert analysis.efficiency_score >= 80

    def test_analyze_tier_efficiency_low_usage_high_cost(self):
        """Test analyzing tier with low usage and high cost (less efficient)."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "count": 10,
            "cost": Decimal("50.00"),
            "success_count": 8,
        }
        
        analysis = analyzer.analyze_tier_efficiency(tier_data, "L3-Coder")
        
        assert analysis.tier_name == "L3-Coder"
        assert analysis.usage_count == 10
        assert analysis.total_cost == Decimal("50.00")
        assert analysis.avg_cost_per_task == Decimal("5.00")
        assert analysis.efficiency_score < 60  # High cost with minimum success rate

    def test_analyze_multiple_tiers(self):
        """Test analyzing multiple tiers at once."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 200,
                "cost": Decimal("5.00"),
                "success_count": 190,
            },
            "L1-Coder": {
                "count": 100,
                "cost": Decimal("25.00"),
                "success_count": 95,
            },
            "L2-Coder": {
                "count": 20,
                "cost": Decimal("30.00"),
                "success_count": 15,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        
        assert len(analyses) == 3
        tier_names = [a.tier_name for a in analyses]
        assert "L0-Coder" in tier_names
        assert "L1-Coder" in tier_names
        assert "L2-Coder" in tier_names

    def test_get_optimization_suggestions(self):
        """Test getting optimization suggestions based on efficiency analysis."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 50,
                "cost": Decimal("1.25"),
                "success_count": 48,
            },
            "L1-Coder": {
                "count": 300,
                "cost": Decimal("75.00"),
                "success_count": 280,
            },
            "L2-Coder": {
                "count": 10,
                "cost": Decimal("15.00"),
                "success_count": 8,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        # Should have at least one suggestion
        assert len(suggestions) >= 1
        
        # Check suggestion structure
        for suggestion in suggestions:
            assert "tier" in suggestion
            assert "message" in suggestion
            assert "priority" in suggestion

    def test_calculate_efficiency_score(self):
        """Test efficiency score calculation."""
        analyzer = TierEfficiencyAnalyzer()
        
        # High efficiency: low cost per task, high success rate
        score = analyzer._calculate_efficiency_score(
            avg_cost_per_task=Decimal("0.01"),
            success_rate=Decimal("0.98")
        )
        
        assert score >= 80  # High score for efficient tier
        
        # Low efficiency: high cost per task, low success rate
        low_score = analyzer._calculate_efficiency_score(
            avg_cost_per_task=Decimal("10.00"),
            success_rate=Decimal("0.50")
        )
        
        assert low_score < 45  # Low score for inefficient tier (high cost + very low success)

    def test_identify_overused_tiers(self):
        """Test identifying overused tiers."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 900,
                "cost": Decimal("22.50"),
                "success_count": 850,
            },
            "L1-Coder": {
                "count": 50,
                "cost": Decimal("12.50"),
                "success_count": 45,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        overused = analyzer.identify_overused_tiers(analyses, threshold=Decimal("0.70"))
        
        # L0-Coder should be identified as overused (900/950 = 95% of usage)
        assert len(overused) >= 1
        assert any(a.tier_name == "L0-Coder" for a in overused)

    def test_identify_underused_tiers(self):
        """Test identifying underused tiers."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 50,
                "cost": Decimal("1.25"),
                "success_count": 48,
            },
            "L3-Coder": {
                "count": 5,
                "cost": Decimal("10.00"),
                "success_count": 4,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        underused = analyzer.identify_underused_tiers(analyses, threshold=Decimal("0.10"))
        
        # L3-Coder should be identified as underused (5/55 = 9% < 10% threshold)
        assert len(underused) >= 1
        assert any(a.tier_name == "L3-Coder" for a in underused)

    def test_tier_ranking_by_efficiency(self):
        """Test ranking tiers by efficiency score."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 200,
                "cost": Decimal("5.00"),
                "success_count": 195,
            },
            "L1-Coder": {
                "count": 100,
                "cost": Decimal("25.00"),
                "success_count": 90,
            },
            "L2-Coder": {
                "count": 50,
                "cost": Decimal("40.00"),
                "success_count": 35,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        sorted_analyses = analyzer.rank_by_efficiency(analyses)
        
        # L0-Coder should be first (most efficient - lowest cost per task)
        assert len(sorted_analyses) == 3
        assert sorted_analyses[0].tier_name == "L0-Coder"


class TestTierEfficiencyIntegration:
    """Test TierEfficiencyAnalyzer integration scenarios."""

    def test_efficiency_analysis_with_realistic_data(self):
        """Test efficiency analysis with realistic usage patterns."""
        analyzer = TierEfficiencyAnalyzer()
        
        tier_data = {
            "L0-Coder": {
                "count": 1000,
                "cost": Decimal("25.00"),
                "success_count": 980,
            },
            "L1-Coder": {
                "count": 500,
                "cost": Decimal("125.00"),
                "success_count": 475,
            },
            "L2-Coder": {
                "count": 100,
                "cost": Decimal("200.00"),
                "success_count": 85,
            },
            "L3-Coder": {
                "count": 10,
                "cost": Decimal("50.00"),
                "success_count": 8,
            }
        }
        
        analyses = analyzer.analyze_all_tiers(tier_data)
        suggestions = analyzer.get_optimization_suggestions(analyses)
        
        # Verify all tiers analyzed
        assert len(analyses) == 4
        
        # Verify we have useful suggestions
        assert len(suggestions) > 0
        
        # Check that L0-Coder is identified as most efficient
        most_efficient = analyzer.rank_by_efficiency(analyses)[0]
        assert most_efficient.tier_name == "L0-Coder"
        assert most_efficient.efficiency_score >= 85
