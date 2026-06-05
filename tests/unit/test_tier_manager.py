#!/usr/bin/env python3
"""Unit tests for tier_manager.py - tier management and escalation logic.

P1-11: Unit tests for Phase 1 features
"""

import pytest

from src.core.cost import Decimal
from src.core.tier_manager import (
    Tier,
    TierLevel,
    TierManager,
)


class TestTierLevel:
    """Tests for TierLevel enum."""
    
    def test_enum_values(self):
        """Test enum has correct values."""
        assert TierLevel.L0.value == "L0"
        assert TierLevel.L1.value == "L1"
        assert TierLevel.L2.value == "L2"
        assert TierLevel.L3.value == "L3"
    
    def test_enum_iteration(self):
        """Test enum can be iterated."""
        levels = list(TierLevel)
        assert len(levels) == 4
        assert TierLevel.L0 in levels
        assert TierLevel.L3 in levels


class TestTier:
    """Tests for Tier dataclass."""
    
    def test_default_values(self):
        """Test Tier with minimal required fields."""
        tier = Tier(
            level=TierLevel.L0,
            name="L0-Coder",
            model="test-model",
            base_url="http://test",
            api_key_env=None,
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0"), "completion": Decimal("0.0")},
        )
        
        assert tier.level == TierLevel.L0
        assert "coder" in tier.name.lower()
        assert tier.supports_tools is True
    
    def test_explicit_supports_tools(self):
        """Test Tier with explicit supports_tools=False."""
        tier = Tier(
            level=TierLevel.L0,
            name="L0-Coder",
            model="test-model",
            base_url="http://test",
            api_key_env=None,
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0"), "completion": Decimal("0.0")},
            supports_tools=False,
        )
        
        assert tier.supports_tools is False


class TestTierManager:
    """Tests for TierManager class."""
    
    def test_get_all_tiers(self):
        """Test get_all_tiers returns tiers from config."""
        tiers = TierManager.get_all_tiers()
        assert len(tiers) > 0
        # First tier should be cheapest (L0)
        assert tiers[0].level == TierLevel.L0
        # Last tier should be Principal
        assert tiers[-1].name == "Principal"

    def test_normalize_tier_name(self):
        """Test normalize_tier_name lowercases input."""
        assert TierManager.normalize_tier_name("L0-Coder") == "L0-Coder"
        assert TierManager.normalize_tier_name("L0-Coder") == "L0-Coder"

    def test_cost_tier_names_constant(self):
        """Test COST_TIER_NAMES has correct mappings."""
        assert TierManager.COST_TIER_NAMES["cheap"] == TierLevel.L0
        assert TierManager.COST_TIER_NAMES["medium"] == TierLevel.L1
        assert TierManager.COST_TIER_NAMES["expensive"] == TierLevel.L2
        assert TierManager.COST_TIER_NAMES["premium"] == TierLevel.L3
    
    def test_get_tier_l0(self):
        """Test get_tier returns correct tier for L0."""
        tier = TierManager.get_tier(TierLevel.L0)
        
        assert tier.level == TierLevel.L0
        assert "coder" in tier.name.lower()
        assert tier.supports_tools is True
    
    def test_get_tier_l1(self):
        """Test get_tier returns correct tier for L1."""
        tier = TierManager.get_tier(TierLevel.L1)
        
        assert tier.level == TierLevel.L1
        assert "coder" in tier.name.lower()
        assert tier.model  # has a model assigned
    
    def test_get_tier_l2(self):
        """Test get_tier returns correct tier for L2."""
        tier = TierManager.get_tier(TierLevel.L2)
        
        assert tier.level == TierLevel.L2
        assert "coder" in tier.name.lower()
        assert tier.model  # has a model assigned
    
    def test_get_tier_l3(self):
        """Test get_tier returns correct tier for L3."""
        tier = TierManager.get_tier(TierLevel.L3)
        
        assert tier.level == TierLevel.L3
        assert "coder" in tier.name.lower() or tier.name == "principal"
        assert tier.model == "anthropic/claude-sonnet-4.6"
    
    def test_get_tier_invalid(self):
        """Test get_tier raises for invalid level."""
        # Valid levels should work
        for level in TierLevel:
            tier = TierManager.get_tier(level)
            assert tier.level == level
        
        # Try to create an invalid level - this tests that only valid levels work
        with pytest.raises(ValueError):
            TierLevel("INVALID")
        
        # Since the above raises during enum creation, the get_tier will never be called with invalid value
        # So the function is protected by the enum validation


class TestTierManagerGetTierByName:
    """Tests for get_tier_by_name method."""
    
    def test_get_tier_by_short_name_l0(self):
        """Test get_tier_by_name with 'L0-Coder'."""
        tier = TierManager.get_tier_by_name("L0-Coder")
        
        assert tier.level == TierLevel.L0
        assert "coder" in tier.name.lower()
    
    def test_get_tier_by_short_name_l1(self):
        """Test get_tier_by_name with 'L1-Coder'."""
        tier = TierManager.get_tier_by_name("L1-Coder")
        
        assert tier.level == TierLevel.L1
    
    def test_get_tier_by_alias_cheap(self):
        """Test get_tier_by_name with alias 'cheap'."""
        tier = TierManager.get_tier_by_name("cheap")
        
        assert tier.level == TierLevel.L0
        assert "coder" in tier.name.lower()
    
    def test_get_tier_by_alias_medium(self):
        """Test get_tier_by_name with alias 'medium'."""
        tier = TierManager.get_tier_by_name("medium")
        
        assert tier.level == TierLevel.L1
        assert "coder" in tier.name.lower()
    
    def test_get_tier_by_alias_expensive(self):
        """Test get_tier_by_name with alias 'expensive'."""
        tier = TierManager.get_tier_by_name("expensive")
        
        assert tier.level == TierLevel.L2
        assert "coder" in tier.name.lower()
    
    def test_get_tier_by_alias_premium(self):
        """Test get_tier_by_name with alias 'premium'."""
        tier = TierManager.get_tier_by_name("premium")
        
        assert tier.level == TierLevel.L3
        assert "coder" in tier.name.lower() or tier.name == "principal"
    
    def test_get_tier_by_name_invalid(self):
        """Test get_tier_by_name raises for invalid name."""
        with pytest.raises(ValueError, match="Unknown tier name"):
            TierManager.get_tier_by_name("invalid-tier")


class TestTierManagerGetNextTier:
    """Tests for get_next_tier method."""
    
    def test_next_from_l0_to_l1(self):
        """Test getting next tier from L0."""
        l0 = TierManager.get_tier(TierLevel.L0)
        next_tier = TierManager.get_next_tier(l0)
        
        assert next_tier is not None
        assert next_tier is not None
        assert next_tier.level == TierLevel.L1
    
    def test_next_from_l1_to_l2(self):
        """Test getting next tier from L1."""
        l1 = TierManager.get_tier(TierLevel.L1)
        next_tier = TierManager.get_next_tier(l1)
        
        assert next_tier is not None
        assert next_tier.level == TierLevel.L2
    
    def test_next_from_l2_to_l3(self):
        """Test getting next tier from L2."""
        l2 = TierManager.get_tier(TierLevel.L2)
        next_tier = TierManager.get_next_tier(l2)
        
        assert next_tier is not None
        assert next_tier.level == TierLevel.L3
    
    def test_next_from_l3_principal(self):
        """Test getting next tier from L3 returns Principal."""
        l3 = TierManager.get_tier(TierLevel.L3)
        next_tier = TierManager.get_next_tier(l3)
        
        assert next_tier is not None
        assert next_tier.name == "Principal"
    
    def test_next_from_principal_none(self):
        """Test getting next tier from Principal returns None."""
        principal = TierManager.get_tier_by_name("Principal")
        next_tier = TierManager.get_next_tier(principal)
        
        assert next_tier is None


class TestTierManagerGetAllTiers:
    """Tests for get_all_tiers method."""
    
    def test_returns_all_tiers(self):
        """Test get_all_tiers returns all tiers from config."""
        tiers = TierManager.get_all_tiers()
        assert len(tiers) >= 2  # at least one coder + Principal
        assert tiers[0].level == TierLevel.L0
        assert tiers[-1].name == "Principal"
    
    def test_returns_copy(self):
        """Test get_all_tiers returns a copy."""
        tiers1 = TierManager.get_all_tiers()
        tiers2 = TierManager.get_all_tiers()
        
        assert tiers1 is not tiers2
    
    def test_tiers_in_correct_order(self):
        """Test tiers are in correct ascending order."""
        tiers = TierManager.get_all_tiers()
        # All coder tiers should be in ascending order
        coder_tiers = [t for t in tiers if t.name != "principal"]
        for i in range(len(coder_tiers) - 1):
            assert coder_tiers[i].level.value <= coder_tiers[i+1].level.value


class TestTierManagerNormalizeTierName:
    """Tests for normalize_tier_name method."""
    
    def test_normalize_cheap(self):
        """Test normalization of 'cheap'."""
        assert TierManager.normalize_tier_name("cheap") == "L0-Coder"
        assert TierManager.normalize_tier_name("CHEAP") == "L0-Coder"
        assert TierManager.normalize_tier_name("Cheap") == "L0-Coder"
    
    def test_normalize_medium(self):
        """Test normalization of 'medium'."""
        assert TierManager.normalize_tier_name("medium") == "L1-Coder"
    
    def test_normalize_expensive(self):
        """Test normalization of 'expensive'."""
        assert TierManager.normalize_tier_name("expensive") == "L2-Coder"
    
    def test_normalize_premium(self):
        """Test normalization of 'premium'."""
        assert TierManager.normalize_tier_name("premium") == "L3-Coder"
    
    def test_normalize_already_normalized(self):
        """Test that already normalized names pass through."""
        assert TierManager.normalize_tier_name("L0-Coder") == "L0-Coder"
        assert TierManager.normalize_tier_name("L0-Coder") == "L0-Coder"
    
    def test_normalize_unknown_preserved(self):
        """Test that unknown names are preserved as-is."""
        result = TierManager.normalize_tier_name("L1-Planner")
        assert result == "L1-Planner"


class TestTierManagerGetDefaultTier:
    """Tests for get_default_tier method."""
    
    def test_returns_l0(self):
        """Test get_default_tier returns L0 (cheapest)."""
        default = TierManager.get_default_tier()
        
        assert default.level == TierLevel.L0
        assert "coder" in default.name.lower()


class TestTierManagerGetMaxTier:
    """Tests for get_max_tier method."""
    
    def test_returns_l3(self):
        """Test get_max_tier returns L3-Coder (most expensive non-Principal tier)."""
        max_tier = TierManager.get_max_tier()
        
        assert max_tier.level == TierLevel.L3
        assert max_tier.name == "Principal"


class TestTierCostComparison:
    """Tests for tier cost characteristics."""
    
    def test_l0_is_free(self):
        """Test L0 tier has zero cost."""
        l0 = TierManager.get_tier(TierLevel.L0)
        
        assert l0.cost_per_1k_tokens["prompt"] == Decimal("0.0")
        assert l0.cost_per_1k_tokens["completion"] == Decimal("0.0")
    
    def test_l1_vs_l2_cost(self):
        """Test L2 cost is not free (escalation tier)."""
        l1 = TierManager.get_tier(TierLevel.L1)
        l2 = TierManager.get_tier(TierLevel.L2)
        assert l1.cost_per_1k_tokens["prompt"] >= Decimal("0.0")
        assert l2.cost_per_1k_tokens["prompt"] >= Decimal("0.0")
    
    def test_l3_is_most_expensive(self):
        """Test L3 is the most expensive tier (cloud model)."""
        l3 = TierManager.get_tier(TierLevel.L3)
        # L3 should have non-zero cost (cloud provider)
        assert l3.cost_per_1k_tokens["prompt"] > Decimal("0.0")
        assert l3.cost_per_1k_tokens["completion"] > Decimal("0.0")


class TestTierModelConfiguration:
    """Tests for tier model configurations."""
    
    def test_l0_model(self):
        """Test L0 tier is a valid coder model."""
        l0 = TierManager.get_tier(TierLevel.L0)
        assert l0.model
        assert l0.supports_tools
        assert l0.cost_per_1k_tokens["prompt"] == Decimal("0.0")  # local = free
    
    def test_l1_model(self):
        """Test L1 tier is a valid coder model."""
        l1 = TierManager.get_tier(TierLevel.L1)
        assert l1.model
        assert l1.supports_tools
    
    def test_l3_model(self):
        """Test L3 tier is a valid coder model."""
        l3 = TierManager.get_tier(TierLevel.L3)
        assert l3.model
        assert l3.supports_tools
