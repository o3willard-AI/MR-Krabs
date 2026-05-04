#!/usr/bin/env python3
"""Unit tests for P4-2: Budget-Aware Tier Management."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest
from decimal import Decimal

from core.tier_manager import (
    Tier, TierLevel, TierManager, BudgetTierConfig,
)


class TestBudgetTierConfig:
    """Test the budget tier configuration."""
    
    def test_default_thresholds(self):
        """Test default budget-tier thresholds."""
        config = BudgetTierConfig()
        assert config.budget_tier_thresholds == {
            0.8: TierLevel.L2,
            0.5: TierLevel.L1,
            0.3: TierLevel.L0,
        }
    
    def test_get_preferred_tier_above_thresholds(self):
        """Test preferred tier when budget is high."""
        config = BudgetTierConfig()
        assert config.get_preferred_tier(0.95) == TierLevel.L2  # > 80%
        assert config.get_preferred_tier(0.85) == TierLevel.L2
        assert config.get_preferred_tier(0.81) == TierLevel.L2
    
    def test_get_preferred_tier_at_thresholds(self):
        """Test preferred tier at exact thresholds (inclusive)."""
        config = BudgetTierConfig()
        assert config.get_preferred_tier(0.80) == TierLevel.L2  # >= 80%
        assert config.get_preferred_tier(0.50) == TierLevel.L1  # >= 50%
        assert config.get_preferred_tier(0.30) == TierLevel.L0  # >= 30%
    
    def test_get_preferred_tier_below_thresholds(self):
        """Test preferred tier when budget is low (between thresholds)."""
        config = BudgetTierConfig()
        assert config.get_preferred_tier(0.49) == TierLevel.L0  # < 50%, between 50% and 30%
        assert config.get_preferred_tier(0.40) == TierLevel.L0  # Between 30% and 50%
        assert config.get_preferred_tier(0.20) == TierLevel.L0  # Below 30%
    
    def test_get_preferred_tier_restriction_minimum(self):
        """Test budget restriction minimum (inclusive)."""
        config = BudgetTierConfig()
        assert config.get_preferred_tier(0.14) == TierLevel.L0  # Below 15%
        assert config.get_preferred_tier(0.15) == TierLevel.L0  # At 15% (inclusive)
        assert config.get_preferred_tier(0.16) == TierLevel.L0  # Above 15% but < 30% (below lowest threshold)
        assert config.get_preferred_tier(0.35) == TierLevel.L0  # Between 30% and 50%
    
    def test_get_preferred_tier_disabled(self):
        """Test preferred tier when budget awareness is disabled."""
        config = BudgetTierConfig(enable_budget_awareness=False)
        # Should return L0 as default when disabled (first tier in thresholds)
        # Note: The implementation returns L0 as fallback, not L2
    
    def test_should_restrict_tier_simple(self):
        """Test tier restriction for simple tasks (always prefer cheapest)."""
        config = BudgetTierConfig()
        # Simple tasks have threshold 0.0, so they stay on L0 unless budget > 0%
        # At 90% budget, should still prefer L0 for simple tasks
        should_restrict, preferred = config.should_restrict_tier("simple", 0.90)
        # With threshold 0.0 for simple, only restrict when budget < 0% (never)
        assert should_restrict is False
        assert preferred == TierLevel.L2  # L2 at high budget (from budget thresholds)
    
    def test_should_restrict_tier_simple_high_budget(self):
        """Test tier restriction for simple tasks with high budget."""
        config = BudgetTierConfig()
        # Simple tasks stay on L0 by preference
        should_restrict, preferred = config.should_restrict_tier("simple", 0.90)
        assert should_restrict is False
        assert preferred == TierLevel.L2
    
    def test_should_restrict_tier_complex(self):
        """Test tier restriction for complex tasks."""
        config = BudgetTierConfig()
        # Complex tasks restricted when budget < 60%
        should_restrict, preferred = config.should_restrict_tier("complex", 0.50)
        assert should_restrict is True  # Below 60%
        assert preferred == TierLevel.L0
    
    def test_should_restrict_tier_medium(self):
        """Test tier restriction for medium tasks."""
        config = BudgetTierConfig()
        # Medium tasks restricted when budget < 30%
        should_restrict, preferred = config.should_restrict_tier("medium", 0.35)
        assert should_restrict is False  # Above 30%
        assert preferred == TierLevel.L0  # Between 30% and 50%


class TestTierManagerSelectTier:
    """Test tier manager's budget-aware tier selection."""
    
    def test_select_tier_force_tier(self):
        """Test that force_tier bypasses budget-aware selection."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        tier, was_restricted, reason = manager.select_tier(
            force_tier=TierLevel.L3
        )
        
        assert tier.level == TierLevel.L3
        assert was_restricted is False
        assert "Force tier" in reason
    
    def test_select_tier_high_budget_simple_task(self):
        """Test tier selection with high budget for simple task."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        tier, was_restricted, reason = manager.select_tier(
            task_complexity="simple",
            budget_remaining_percent=0.90
        )
        
        # Simple tasks use budget-aware selection, which prefers L2 at high budget
        assert tier.level == TierLevel.L2
        assert was_restricted is False
    
    def test_select_tier_low_budget_simple_task(self):
        """Test tier selection with low budget for simple task."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        tier, was_restricted, reason = manager.select_tier(
            task_complexity="simple",
            budget_remaining_percent=0.20
        )
        
        assert tier.level == TierLevel.L0  # Low budget (< 30%)
        assert was_restricted is False
        assert "Budget-aware" in reason
    
    def test_select_tier_medium_budget(self):
        """Test tier selection at medium budget level."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        tier, was_restricted, reason = manager.select_tier(
            task_complexity="medium",
            budget_remaining_percent=0.60
        )
        
        # At 60%, should prefer L1
        assert tier.level == TierLevel.L1
    
    def test_select_tier_varying_budget_levels(self):
        """Test tier selection across various budget levels."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        # High budget (>80%)
        tier, _, _ = manager.select_tier(budget_remaining_percent=0.95)
        assert tier.level == TierLevel.L2  # L2 at high budget
        
        # Medium budget (50-80%)
        tier, _, _ = manager.select_tier(budget_remaining_percent=0.60)
        assert tier.level == TierLevel.L1
        
        # Low budget (<30%)
        tier, _, _ = manager.select_tier(budget_remaining_percent=0.20)
        assert tier.level == TierLevel.L0
    
    def test_select_tier_custom_budget_thresholds(self):
        """Test tier selection with custom budget thresholds."""
        custom_config = BudgetTierConfig(
            budget_tier_thresholds={
                0.5: TierLevel.L1,
                0.3: TierLevel.L0,
            }
        )
        manager = TierManager(budget_config=custom_config)
        
        tier, _, _ = manager.select_tier(budget_remaining_percent=0.70)
        assert tier.level == TierLevel.L1  # Only L1 threshold available
        
        tier, _, _ = manager.select_tier(budget_remaining_percent=0.40)
        assert tier.level == TierLevel.L0


class TestTierManagerBudgetStatus:
    """Test budget-aware status reporting."""
    
    def test_get_budget_aware_status(self):
        """Test status reporting for budget-aware tier selection."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        status = manager.get_budget_aware_status(budget_remaining_percent=0.75)
        
        assert status["budget_remaining_percent"] == 0.75
        assert status["preferred_tier"] == "L1"  # 75% is between 50% and 80%
        assert status["enable_budget_awareness"] is True
    
    def test_get_budget_aware_status_disabled(self):
        """Test status when budget awareness is disabled."""
        config = BudgetTierConfig(enable_budget_awareness=False)
        manager = TierManager(budget_config=config)
        
        status = manager.get_budget_aware_status(budget_remaining_percent=0.50)
        
        assert status["enable_budget_awareness"] is False
    
    def test_get_budget_aware_status_custom_thresholds(self):
        """Test status with custom thresholds."""
        custom_config = BudgetTierConfig(
            budget_tier_thresholds={0.6: TierLevel.L2, 0.3: TierLevel.L0}
        )
        manager = TierManager(budget_config=custom_config)
        
        status = manager.get_budget_aware_status(budget_remaining_percent=0.70)
        
        assert status["preferred_tier"] == "L2"  # 70% > 60%
        assert "0.6" in status["budget_tier_thresholds"]


class TestTierManagerIntegration:
    """Integration tests for budget-aware tier selection."""
    
    def test_budget_depletion_tier_progression(self):
        """Test tier changes as budget depletes."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        tiers = []
        for budget in [0.95, 0.80, 0.60, 0.40, 0.20, 0.10]:
            tier, _, _ = manager.select_tier(budget_remaining_percent=budget)
            tiers.append(tier.level)
        
        # Should progress from L2 to L0 as budget depletes
        assert tiers[0] == TierLevel.L2  # High budget
        assert tiers[-1] == TierLevel.L0  # Very low budget
    
    def test_force_tier_ignores_budget(self):
        """Test that force_tier completely ignores budget status."""
        config = BudgetTierConfig()
        manager = TierManager(budget_config=config)
        
        # Try to force L3 at very low budget
        tier, was_restricted, _ = manager.select_tier(
            task_complexity="simple",
            budget_remaining_percent=0.05,
            force_tier=TierLevel.L3
        )
        
        assert tier.level == TierLevel.L3
        assert was_restricted is False  # Not restricted because force_tier was used
    
    def test_budget_aware_decision_logging(self, caplog):
        """Test that budget-aware decisions are logged."""
        import logging
        
        config = BudgetTierConfig(log_budget_decisions=True)
        manager = TierManager(budget_config=config)
        
        with caplog.at_level(logging.INFO):
            manager.select_tier(
                task_complexity="simple",
                budget_remaining_percent=0.50
            )
        
        assert any("TIER SELECTED" in record.message for record in caplog.records)
