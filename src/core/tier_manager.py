#!/usr/bin/env python3
"""Tier management for cost-optimized orchestration.

Defines tier hierarchy, models, and escalation logic with budget awareness.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional

from src.core.model_capabilities import MODEL_REGISTRY, get_capable_models

logger = logging.getLogger(__name__)


class TierLevel(Enum):
    """Cost tier levels from cheapest to most expensive."""
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass
class Tier:
    """Configuration for a single execution tier."""
    
    level: TierLevel
    name: str  # e.g., "L0-Coder", "L1-Coder"
    model: str
    base_url: str
    api_key_env: Optional[str]
    temperature: float
    cost_per_1k_tokens: Dict[str, Decimal]
    supports_tools: bool = True


@dataclass
class BudgetTierConfig:
    """Configuration for budget-aware tier selection."""
    
    # Map of budget percentage thresholds to preferred tier levels
    # Example: {0.3: "L0", 0.5: "L1", 0.8: "L2"}
    # Means: if budget > 80% remaining, can use L2; if 50-80%, use L1; if < 30%, use L0
    budget_tier_thresholds: Dict[Decimal, TierLevel] = field(default_factory=lambda: {
        Decimal("0.8"): TierLevel.L2,
        Decimal("0.5"): TierLevel.L1,
        Decimal("0.3"): TierLevel.L0,
    })
    
    # Simple task classification (tasks that don't need high intelligence)
    # These are candidates for budget-aware tier reduction
    simple_task_thresholds: Dict[str, Decimal] = field(default_factory=lambda: {
        "simple": Decimal("0.0"),  # Always prefer cheapest for simple tasks
        "medium": Decimal("0.3"),  # Use cheap tier unless budget > 30%
        "complex": Decimal("0.6"),  # Only use expensive tier if budget > 60%
    })
    
    # Budget-aware tier preference settings
    enable_budget_awareness: bool = True
    budget_restriction_minimum: Decimal = Decimal("0.15")  # Below 15%, restrict to L0 unless forced
    
    # Log budget-aware decisions
    log_budget_decisions: bool = True
    
    def get_preferred_tier(self, budget_remaining_percent: Decimal) -> TierLevel:
        """Get preferred tier level based on budget remaining percentage."""
        if not self.enable_budget_awareness:
            return TierLevel.L1  # Default to medium tier
        
        # If budget is very low, restrict to cheapest tier
        if budget_remaining_percent <= self.budget_restriction_minimum:
            return TierLevel.L0
        
        # Find highest threshold that budget exceeds (>= comparison for exact match)
        preferred_tier = TierLevel.L0  # Default to cheapest
        for threshold, tier in sorted(self.budget_tier_thresholds.items(), reverse=True):
            if budget_remaining_percent >= threshold:
                preferred_tier = tier
                break
        
        return preferred_tier
    
    def should_restrict_tier(self, task_complexity: str, budget_remaining_percent: Decimal) -> tuple[bool, TierLevel]:
        """
        Determine if tier should be restricted based on budget and task complexity.
        
        Returns:
            (should_restrict, preferred_tier)
        """
        if not self.enable_budget_awareness:
            return (False, TierLevel.L2)
        
        # Get base preferred tier from budget
        preferred_tier = self.get_preferred_tier(budget_remaining_percent)
        
        # Apply task complexity adjustments
        complexity_threshold = self.simple_task_thresholds.get(task_complexity.lower(), Decimal("0.5"))
        
        if budget_remaining_percent < complexity_threshold:
            return (True, TierLevel.L0)
        
        return (False, preferred_tier)


class TierManager:
    """Manages tier hierarchy and escalation logic with budget awareness."""
    
    # Predefined tier hierarchy (cheapest to most expensive)
    TIER_ORDER = [
        Tier(
            level=TierLevel.L0,
            name="L0-Coder",
            model="qwen/qwen3-coder-30b",
            base_url="http://192.168.101.21:1234/v1",  # LM Studio (local, free)
            api_key_env=None,
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0"), "completion": Decimal("0.0")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L1,
            name="L1-Coder",
            model="x-ai/grok-4.1-fast",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.002"), "completion": Decimal("0.006")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L2,
            name="L2-Coder",
            model="minimax/minimax-m2.7",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.0002"), "completion": Decimal("0.0006")},
            supports_tools=True
        ),
        Tier(
            level=TierLevel.L3,
            name="L3-Coder",
            model="anthropic/claude-sonnet-4.6",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.7,
            cost_per_1k_tokens={"prompt": Decimal("0.003"), "completion": Decimal("0.015")},
            supports_tools=True
        ),
    ]
    
    # Simplified tier name aliases (for easier usage)
    TIER_ALIASES: Dict[str, str] = {
        "cheap": "L0-Coder",
        "medium": "L1-Coder",
        "expensive": "L2-Coder",
        "premium": "L3-Coder",
    }
    
    # Cost tier aliases mapping to actual tier names
    COST_TIER_NAMES = {
        "cheap": TierLevel.L0,
        "medium": TierLevel.L1,
        "expensive": TierLevel.L2,
        "premium": TierLevel.L3,
    }
    
    def __init__(self, budget_config: Optional[BudgetTierConfig] = None):
        """Initialize tier manager with optional budget configuration."""
        self.budget_config = budget_config or BudgetTierConfig()
    
    @classmethod
    def get_tier(cls, level: TierLevel) -> Tier:
        """Get tier configuration by level."""
        for tier in cls.TIER_ORDER:
            if tier.level == level:
                return tier
        raise ValueError(f"Unknown tier level: {level}")
    
    @classmethod
    def get_tier_by_name(cls, name: str) -> Tier:
        """Get tier configuration by name (e.g., 'L0-Coder')."""
        normalized_name = cls.normalize_tier_name(name)
        for tier in cls.TIER_ORDER:
            if tier.name == normalized_name:
                return tier
        raise ValueError(f"Unknown tier name: {name}")
    
    @classmethod
    def get_next_tier(cls, current_tier: Tier) -> Optional[Tier]:
        """Get next more expensive tier, or None if already at L3."""
        current_index = cls.TIER_ORDER.index(current_tier)
        if current_index < len(cls.TIER_ORDER) - 1:
            return cls.TIER_ORDER[current_index + 1]
        return None
    
    @classmethod
    def get_all_tiers(cls) -> list[Tier]:
        """Get all tiers in order from cheapest to most expensive."""
        return cls.TIER_ORDER.copy()
    
    @classmethod
    def normalize_tier_name(cls, tier: str) -> str:
        """Convert simplified names to actual tier names.
        
        Examples:
            'cheap' -> 'L0-Coder'
            'L0-Coder' -> 'L0-Coder' (no change)
            'L1-Planner' -> 'L1-Planner' (no change, not in aliases)
        """
        return cls.TIER_ALIASES.get(tier.lower(), tier)
    
    @classmethod
    def get_default_tier(cls) -> Tier:
        """Get the default starting tier (cheapest capable)."""
        return cls.TIER_ORDER[0]
    
    @classmethod
    def get_max_tier(cls) -> Tier:
        """Get the maximum tier (most expensive)."""
        return cls.TIER_ORDER[-1]

    def find_capable_model(self, tier_level: TierLevel, token_count: int = 0, requires_tools: bool = False) -> str | None:
        """
        Find a model within the specified tier that can handle the requirements.
        
        If no capable model is found in the current tier, escalate to the next tier
        until a capable model is found or all tiers are exhausted.
        
        Args:
            tier_level: The starting tier level to search from
            token_count: Required context size (in tokens)
            requires_tools: Whether the task requires tool calling support
            
        Returns:
            Model ID string if found, None otherwise
        """
        # Find the starting tier
        current_tier = self.get_tier(tier_level)
        
        # Check if the current tier's model can handle the requirements
        current_model_id = current_tier.model
        capability = MODEL_REGISTRY.get(current_model_id)
        
        # If we have capability data for this model, check if it meets requirements
        if capability is not None:
            if token_count > 0 and not capability.can_handle_context(token_count):
                # Context window too small - skip to next tier
                pass
            elif not capability.can_handle_task(requires_tools=requires_tools):
                # Tool calling not supported - skip to next tier
                pass
            else:
                # Model is capable, return it
                return current_model_id
        
        # If we can't use the current tier's model, look for a capable model in higher tiers
        current_index = self.TIER_ORDER.index(current_tier)
        for i in range(current_index + 1, len(self.TIER_ORDER)):
            next_tier = self.TIER_ORDER[i]
            next_model_id = next_tier.model
            
            # Check if this tier's model can handle the requirements
            capability = MODEL_REGISTRY.get(next_model_id)
            if capability is not None:
                if token_count > 0 and not capability.can_handle_context(token_count):
                    continue  # Skip this tier, context window too small
                if not capability.can_handle_task(requires_tools=requires_tools):
                    continue  # Skip this tier, tool calling not supported
                return next_model_id  # Found a capable model
        
        # If we get here, no capable model found in any tier
        return None
    
    def select_tier(self, task_complexity: str = "medium", budget_remaining_percent: Decimal = Decimal("1.0"),
                    force_tier: Optional[TierLevel] = None) -> tuple[Tier, bool, str]:
        """
        Select tier based on budget awareness and task complexity.
        
        Args:
            task_complexity: Task type ("simple", "medium", "complex")
            budget_remaining_percent: Percentage of budget remaining (0.0 to 1.0)
            force_tier: Optional tier override (bypasses budget-aware selection)
        
        Returns:
            (selected_tier, was_restricted, reason)
        """
        # If force_tier is provided, use it directly
        if force_tier:
            tier = self.get_tier(force_tier)
            return (tier, False, f"Force tier requested: {force_tier.value}")
        
        # Get budget-aware preferences
        should_restrict, preferred_tier = self.budget_config.should_restrict_tier(
            task_complexity, budget_remaining_percent
        )
        
        # Determine selected tier
        if should_restrict:
            selected_tier = self.get_tier(TierLevel.L0)
            reason = f"Budget restriction (<{self.budget_config.simple_task_thresholds.get(task_complexity.lower(), Decimal('0.5'))*100:.0f}%): selecting L0"
            was_restricted = True
        else:
            selected_tier = self.get_tier(preferred_tier)
            was_restricted = False
            reason = f"Budget-aware selection at {budget_remaining_percent*100:.0f}% remaining: {preferred_tier.value}"
        
        # Log decision if configured
        if self.budget_config.log_budget_decisions:
            logger.info(f"[TIER SELECTED] {reason} | Task: {task_complexity} | Budget: {budget_remaining_percent*100:.1f}%")
        
        return (selected_tier, was_restricted, reason)
    
    def get_budget_aware_status(self, budget_remaining_percent: Decimal) -> Dict:
        """Get budget-aware tier selection status."""
        preferred_tier = self.budget_config.get_preferred_tier(budget_remaining_percent)
        
        return {
            "budget_remaining_percent": float(budget_remaining_percent),
            "preferred_tier": preferred_tier.value,
            "enable_budget_awareness": self.budget_config.enable_budget_awareness,
            "budget_tier_thresholds": {str(k): v.value for k, v in self.budget_config.budget_tier_thresholds.items()},
        }
