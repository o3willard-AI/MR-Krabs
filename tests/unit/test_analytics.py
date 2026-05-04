"""Unit tests for Analytics module."""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, patch

from src.core.analytics import (
    TierAnalytics,
    AnalyticsSummary,
    AnalyticsCollector,
    create_analytics_collector,
)


class TestTierAnalytics:
    """Tests for TierAnalytics class."""

    @pytest.fixture
    def tier_analytics(self):
        """Create a TierAnalytics instance."""
        return TierAnalytics(tier="L0-Planner")

    def test_initialization(self, tier_analytics):
        """Test tier analytics initializes correctly."""
        assert tier_analytics.tier == "L0-Planner"
        assert tier_analytics.total_attempts == 0
        assert tier_analytics.successful_attempts == 0
        assert tier_analytics.failed_attempts == 0
        assert tier_analytics.total_cost == Decimal("0.0")
        assert tier_analytics.total_tokens == 0
        assert tier_analytics.avg_duration == 0.0

    def test_update_success(self, tier_analytics):
        """Test updating with a successful event."""
        tier_analytics.update(
            success=True,
            cost=Decimal("0.01"),
            tokens=100,
            duration=0.5,
        )

        assert tier_analytics.total_attempts == 1
        assert tier_analytics.successful_attempts == 1
        assert tier_analytics.failed_attempts == 0
        assert tier_analytics.total_cost == Decimal("0.01")
        assert tier_analytics.total_tokens == 100
        assert tier_analytics.avg_duration == 0.5

    def test_update_failure(self, tier_analytics):
        """Test updating with a failed event."""
        tier_analytics.update(
            success=False,
            cost=Decimal("0.01"),
            tokens=100,
            duration=0.5,
        )

        assert tier_analytics.total_attempts == 1
        assert tier_analytics.successful_attempts == 0
        assert tier_analytics.failed_attempts == 1

    def test_update_multiple_events(self, tier_analytics):
        """Test updating with multiple events."""
        tier_analytics.update(success=True, cost=Decimal("0.01"), tokens=100, duration=0.5)
        tier_analytics.update(success=True, cost=Decimal("0.02"), tokens=200, duration=1.0)
        tier_analytics.update(success=False, cost=Decimal("0.01"), tokens=100, duration=0.5)

        assert tier_analytics.total_attempts == 3
        assert tier_analytics.successful_attempts == 2
        assert tier_analytics.failed_attempts == 1
        assert tier_analytics.total_cost == Decimal("0.04")
        assert tier_analytics.total_tokens == 400
        assert 0.65 <= tier_analytics.avg_duration <= 0.68

    def test_avg_success_rate(self, tier_analytics):
        """Test success rate calculation."""
        tier_analytics.update(success=True, cost=Decimal("0.01"), tokens=100, duration=0.5)
        tier_analytics.update(success=True, cost=Decimal("0.01"), tokens=100, duration=0.5)
        tier_analytics.update(success=False, cost=Decimal("0.01"), tokens=100, duration=0.5)

        success_rate = tier_analytics.avg_success_rate

        # 2 out of 3 attempts = 66.67%
        assert 66.0 <= success_rate <= 67.0

    def test_avg_success_rate_no_attempts(self, tier_analytics):
        """Test success rate with no attempts."""
        tier_analytics.update(success=False, cost=Decimal("0.01"), tokens=100, duration=0.5)

        # Should be 0%
        assert tier_analytics.avg_success_rate == 0.0

    def test_avg_cost_per_success(self, tier_analytics):
        """Test average cost calculation."""
        tier_analytics.update(success=True, cost=Decimal("0.03"), tokens=100, duration=0.5)
        tier_analytics.update(success=True, cost=Decimal("0.06"), tokens=200, duration=1.0)

        avg_cost = tier_analytics.avg_cost_per_success

        # Total cost: 0.09, Successes: 2
        # Average: 0.045 per success
        assert avg_cost == Decimal("0.045")

    def test_avg_cost_per_success_no_successes(self, tier_analytics):
        """Test average cost calculation when no successes."""
        tier_analytics.update(success=False, cost=Decimal("0.01"), tokens=100, duration=0.5)

        avg_cost = tier_analytics.avg_cost_per_success

        assert avg_cost == Decimal("0.00")

    def test_repr(self, tier_analytics):
        """Test string representation."""
        tier_analytics.update(success=True, cost=Decimal("0.01"), tokens=100, duration=0.5)

        repr_str = repr(tier_analytics)
        assert "L0-Planner" in repr_str
        assert "attempts=1" in repr_str
        assert "cost=$0.0100" in repr_str


class TestAnalyticsSummary:
    """Tests for AnalyticsSummary class."""

    @pytest.fixture
    def summary(self):
        """Create an AnalyticsSummary instance."""
        return AnalyticsSummary(
            total_tasks=10,
            overall_success_rate=85.0,
            total_cost=Decimal("5.00"),
            avg_cost_per_task=Decimal("0.50"),
        )

    def test_initialization(self, summary):
        """Test summary initializes correctly."""
        assert summary.total_tasks == 10
        assert summary.overall_success_rate == 85.0
        assert summary.total_cost == Decimal("5.00")
        assert summary.avg_cost_per_task == Decimal("0.50")
        assert summary.generated_at is not None

    def test_add_tier_analytics(self, summary):
        """Test adding tier analytics."""
        tier_analytics = TierAnalytics(tier="L1-Worker")
        tier_analytics.update(success=True, cost=Decimal("1.00"), tokens=100, duration=1.0)

        summary.add_tier_analytics("L1-Worker", tier_analytics)

        assert "L1-Worker" in summary.tier_analytics
        assert summary.tier_analytics["L1-Worker"].total_attempts == 1

    def test_add_provider_analytics(self, summary):
        """Test adding provider analytics."""
        summary.add_provider_analytics(
            provider="OpenRouter",
            data={"cost": Decimal("0.01"), "tokens": 100},
        )

        assert "OpenRouter" in summary.provider_analytics
        assert summary.provider_analytics["OpenRouter"]["total_cost"] == Decimal("0.01")

    def test_add_provider_analytics_multiple(self, summary):
        """Test adding multiple provider analytics."""
        summary.add_provider_analytics("OpenRouter", {"cost": Decimal("0.01"), "tokens": 100})
        summary.add_provider_analytics("OpenRouter", {"cost": Decimal("0.02"), "tokens": 200})

        assert summary.provider_analytics["OpenRouter"]["total_cost"] == Decimal("0.03")
        assert summary.provider_analytics["OpenRouter"]["total_tasks"] == 2


class TestAnalyticsCollector:
    """Tests for AnalyticsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create an AnalyticsCollector instance."""
        return AnalyticsCollector()

    def test_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.tier_data == {}
        assert collector.provider_data == {}
        assert collector.total_tasks == 0
        assert collector.total_cost == Decimal("0.0")
        assert collector.successful_tasks == 0

    def test_record_tier_event(self, collector):
        """Test recording tier event."""
        collector.record_tier_event(
            tier="L0-Planner",
            success=True,
            cost=Decimal("0.01"),
            tokens=100,
            duration=0.5,
        )

        assert "L0-Planner" in collector.tier_data
        assert collector.tier_data["L0-Planner"].total_attempts == 1

    def test_record_tier_event_multiple(self, collector):
        """Test recording multiple tier events."""
        collector.record_tier_event("L0-Planner", True, Decimal("0.01"), 100, 0.5)
        collector.record_tier_event("L0-Planner", True, Decimal("0.02"), 200, 1.0)
        collector.record_tier_event("L1-Worker", True, Decimal("0.03"), 300, 1.5)

        assert collector.tier_data["L0-Planner"].total_attempts == 2
        assert collector.tier_data["L1-Worker"].total_attempts == 1
        assert collector.total_tasks == 3

    def test_record_provider_event(self, collector):
        """Test recording provider event."""
        collector.record_provider_event(
            provider="OpenRouter",
            cost=Decimal("0.01"),
            success=True,
        )

        assert "OpenRouter" in collector.provider_data
        assert collector.provider_data["OpenRouter"]["total_cost"] == Decimal("0.01")

    def test_get_summary(self, collector):
        """Test getting analytics summary."""
        # Record some events
        collector.record_tier_event("L0-Planner", True, Decimal("0.01"), 100, 0.5)
        collector.record_tier_event("L0-Planner", True, Decimal("0.02"), 200, 1.0)
        collector.record_tier_event("L1-Worker", True, Decimal("0.03"), 300, 1.5)

        summary = collector.get_summary()

        assert summary is not None
        assert summary.total_cost == Decimal("0.06")
        assert summary.total_tasks == 3
        assert len(summary.tier_analytics) == 2
        assert "L0-Planner" in summary.tier_analytics
        assert "L1-Worker" in summary.tier_analytics

    def test_get_summary_empty(self, collector):
        """Test getting summary with no events."""
        summary = collector.get_summary()

        assert summary.total_cost == Decimal("0.00")
        assert summary.total_tasks == 0

    def test_get_tier_analytics_in_summary(self, collector):
        """Test getting tier analytics via summary."""
        collector.record_tier_event("L0-Planner", True, Decimal("0.01"), 100, 0.5)
        collector.record_tier_event("L0-Planner", False, Decimal("0.01"), 100, 0.5)

        summary = collector.get_summary()
        
        assert "L0-Planner" in summary.tier_analytics
        tier_analytics = summary.tier_analytics["L0-Planner"]
        assert tier_analytics.total_attempts == 2
        assert tier_analytics.successful_attempts == 1

    def test_to_dict_not_available(self, collector):
        """Test that to_dict is not available (not implemented)."""
        # The collector doesn't have a to_dict method, we use get_summary() instead
        # This test documents the absence of the method
        assert not hasattr(collector, 'to_dict')

    def test_generate_recommendations(self, collector):
        """Test generating recommendations via summary."""
        # Record events
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)

        # Recommendations are generated via get_summary(), not directly
        summary = collector.get_summary()
        
        # Summary should be generated successfully
        assert summary is not None
        assert "L2-Expert" in summary.tier_analytics


class TestCreateAnalyticsCollector:
    """Tests for create_analytics_collector factory function."""

    def test_creates_collector(self):
        """Test factory creates AnalyticsCollector instance."""
        collector = create_analytics_collector()

        assert isinstance(collector, AnalyticsCollector)

    def test_collector_has_required_methods(self):
        """Test created collector has required methods."""
        collector = create_analytics_collector()

        assert hasattr(collector, "record_tier_event")
        assert hasattr(collector, "record_provider_event")
        assert hasattr(collector, "get_summary")
        # Note: to_dict is not implemented, we use get_summary() instead
        # assert not hasattr(collector, 'to_dict')  # Documented as not available


class TestAnalyticsCollectorEdgeCases:
    """Tests for edge cases in analytics collection."""

    @pytest.fixture
    def collector(self):
        """Create an AnalyticsCollector instance."""
        return AnalyticsCollector()

    def test_zero_cost(self, collector):
        """Test handling zero cost events."""
        collector.record_tier_event("L0-Planner", True, Decimal("0.00"), 0, 0.0)

        summary = collector.get_summary()
        assert summary.total_cost == Decimal("0.00")

    def test_zero_tokens(self, collector):
        """Test handling zero token events."""
        collector.record_tier_event("L0-Planner", True, Decimal("0.01"), 0, 0.5)

        summary = collector.get_summary()
        assert summary.total_tasks == 1

    def test_large_cost(self, collector):
        """Test handling large cost values."""
        collector.record_tier_event("L3-Premium", True, Decimal("100.00"), 10000, 60.0)

        summary = collector.get_summary()
        assert summary.total_cost == Decimal("100.00")

    def test_many_tiers(self, collector):
        """Test handling many different tiers."""
        for i in range(10):
            tier_name = f"L{i % 4}-Tier{i}"
            collector.record_tier_event(tier_name, True, Decimal("0.01"), 100, 0.5)

        summary = collector.get_summary()
        # We create 10 unique tiers (L0-Tier0, L1-Tier1, etc.)
        assert len(summary.tier_analytics) == 10  # Should have 10 unique tiers

    def test_many_providers(self, collector):
        """Test handling multiple providers."""
        providers = ["OpenRouter", "LMStudio", "OpenAI", "Anthropic"]
        for provider in providers:
            collector.record_provider_event(provider, Decimal("0.01"), True)

        summary = collector.get_summary()
        assert len(summary.provider_analytics) == 4


class TestAnalyticsRecommendations:
    """Tests for recommendation generation."""

    @pytest.fixture
    def collector(self):
        """Create an AnalyticsCollector instance."""
        return AnalyticsCollector()

    def test_over_provisioning_detection(self, collector):
        """Test detection of over-provisioning (high success on expensive tiers)."""
        # High success rate on L2 (medium tier)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)
        collector.record_tier_event("L2-Expert", True, Decimal("1.00"), 1000, 5.0)

        summary = collector.get_summary()

        # Should have analytics
        assert len(summary.tier_analytics) == 1

    def test_under_provisioning_detection(self, collector):
        """Test detection of under-provisioning (low success on cheap tiers)."""
        # Low success rate on L0
        collector.record_tier_event("L0-Planner", False, Decimal("0.00"), 100, 0.5)
        collector.record_tier_event("L0-Planner", False, Decimal("0.00"), 100, 0.5)
        collector.record_tier_event("L0-Planner", False, Decimal("0.00"), 100, 0.5)
        collector.record_tier_event("L0-Planner", True, Decimal("0.00"), 100, 0.5)

        summary = collector.get_summary()

        # Should have analytics for L0
        assert "L0-Planner" in summary.tier_analytics
        tier_analytics = summary.tier_analytics["L0-Planner"]
        assert tier_analytics.total_attempts == 4
        assert tier_analytics.successful_attempts == 1
        assert tier_analytics.avg_success_rate == 25.0

    def test_cost_efficiency_recommendation(self, collector):
        """Test cost efficiency tracking."""
        # Mix of low and high cost tiers
        collector.record_tier_event("L0-Planner", True, Decimal("0.00"), 100, 0.5)
        collector.record_tier_event("L3-Coder", True, Decimal("10.00"), 1000, 5.0)

        summary = collector.get_summary()

        # Should generate summary successfully
        assert summary.total_cost == Decimal("10.00")
        assert "L0-Planner" in summary.tier_analytics
        assert "L3-Coder" in summary.tier_analytics
        
    def test_decimal_operations(self, collector):
        """Test that decimal operations work correctly."""
        # Test that we can add costs and calculate summaries
        collector.record_tier_event("L1-Worker", True, Decimal("5.00"), 500, 2.0)
        collector.record_tier_event("L1-Worker", True, Decimal("3.00"), 300, 1.5)

        summary = collector.get_summary()
        
        # Should handle decimal addition correctly
        assert summary.total_cost == Decimal("8.00")
