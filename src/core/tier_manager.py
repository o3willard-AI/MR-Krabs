#!/usr/bin/env python3
"""Tier management for cost-optimized orchestration.

Phase D: All tier definitions come from ~/.mrkrabs/config.yaml.
TIER_ORDER and TIER_ALIASES are derived dynamically from the config.
"""

import logging
import re
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
    name: str  # e.g., "l0-coder", "l1-coder"
    model: str
    base_url: str
    api_key_env: Optional[str]
    temperature: float
    cost_per_1k_tokens: Dict[str, Decimal]
    supports_tools: bool = True


@dataclass
class BudgetTierConfig:
    """Configuration for budget-aware tier selection."""

    budget_tier_thresholds: Dict[Decimal, TierLevel] = field(default_factory=lambda: {
        Decimal("0.8"): TierLevel.L2,
        Decimal("0.5"): TierLevel.L1,
        Decimal("0.3"): TierLevel.L0,
    })

    simple_task_thresholds: Dict[str, Decimal] = field(default_factory=lambda: {
        "simple": Decimal("0.0"),
        "medium": Decimal("0.3"),
        "complex": Decimal("0.6"),
    })

    enable_budget_awareness: bool = True
    budget_restriction_minimum: Decimal = Decimal("0.15")
    log_budget_decisions: bool = True

    def get_preferred_tier(self, budget_remaining_percent: Decimal) -> TierLevel:
        if not self.enable_budget_awareness:
            return TierLevel.L1
        if budget_remaining_percent <= self.budget_restriction_minimum:
            return TierLevel.L0
        preferred_tier = TierLevel.L0
        for threshold, tier in sorted(self.budget_tier_thresholds.items(), reverse=True):
            if budget_remaining_percent >= threshold:
                preferred_tier = tier
                break
        return preferred_tier

    def should_restrict_tier(self, task_complexity: str, budget_remaining_percent: Decimal) -> tuple[bool, TierLevel]:
        if not self.enable_budget_awareness:
            return (False, TierLevel.L2)
        preferred_tier = self.get_preferred_tier(budget_remaining_percent)
        complexity_threshold = self.simple_task_thresholds.get(task_complexity.lower(), Decimal("0.5"))
        if budget_remaining_percent < complexity_threshold:
            return (True, TierLevel.L0)
        return (False, preferred_tier)


class TierManager:
    """Manages tier hierarchy and escalation logic with budget awareness.

    Phase D: Tiers are derived from ~/.mrkrabs/config.yaml at runtime.
    No hardcoded TIER_ORDER or TIER_ALIASES.
    """

    @classmethod
    def _get_config(cls):
        """Lazy-load the config."""
        from src.core.config_loader import get_config
        return get_config()

    @classmethod
    def _build_tiers(cls) -> list[Tier]:
        """Build Tier list from config models."""
        config = cls._get_config()
        tiers: list[Tier] = []
        seen = set()

        # Collect all coder-tier models sorted by tier number
        coder_models = [
            (cls._extract_tier_num(k), k, m)
            for k, m in config.models.items()
            if "coder" in m.roles
        ]
        coder_models.sort(key=lambda x: x[0])

        for tier_num, key, model in coder_models:
            if key in seen:
                continue
            seen.add(key)

            # De-duplicate: only keep first model per tier level
            level = TierLevel(f"L{tier_num}")
            if any(t.level == level for t in tiers):
                continue

            provider = config.providers.get(model.provider)
            base_url = provider.base_url if provider else ""

            # Determine cost (free for local, estimated for cloud)
            is_local = "1234" in base_url or "localhost" in base_url
            prompt_cost = Decimal("0.0") if is_local else Decimal("0.000002")
            completion_cost = Decimal("0.0") if is_local else Decimal("0.000006")

            tiers.append(Tier(
                level=TierLevel(f"L{tier_num}"),
                name=f"l{tier_num}-coder",
                model=model.model,
                base_url=base_url,
                api_key_env=provider.api_key_env if provider else None,
                temperature=model.temperature,
                cost_per_1k_tokens={"prompt": prompt_cost, "completion": completion_cost},
                supports_tools=bool(model.tools),
            ))

        # Add Principal as final tier
        tiers.append(Tier(
            level=TierLevel.L3,
            name="Principal",
            model="<principal-agent>",
            base_url="<principal-agent>",
            api_key_env=None,
            temperature=0.0,
            cost_per_1k_tokens={"prompt": Decimal("0.0"), "completion": Decimal("0.0")},
            supports_tools=False,
        ))

        return tiers

    @classmethod
    def _extract_tier_num(cls, key: str) -> int:
        """Extract tier number from key: l0-coder → 0, l2-planner → 2."""
        match = re.match(r"l(\d+)", key.lower())
        return int(match.group(1)) if match else 0

    @classmethod
    def get_tier(cls, level: TierLevel) -> Tier:
        for tier in cls._build_tiers():
            if tier.level == level:
                return tier
        raise ValueError(f"Unknown tier level: {level}")

    @classmethod
    def get_tier_by_name(cls, name: str) -> Tier:
        normalized = cls.normalize_tier_name(name).lower()
        for tier in cls._build_tiers():
            if tier.name.lower() == normalized:
                return tier
        raise ValueError(f"Unknown tier name: {name}")

    @classmethod
    def get_next_tier(cls, current_tier: Tier) -> Optional[Tier]:
        tiers = cls._build_tiers()
        current_index = tiers.index(current_tier) if current_tier in tiers else -1
        if current_index >= 0 and current_index < len(tiers) - 1:
            return tiers[current_index + 1]
        return None

    @classmethod
    def get_all_tiers(cls) -> list[Tier]:
        return cls._build_tiers()

    # Cost tier aliases mapping to actual tier levels
    COST_TIER_NAMES = {
        "cheap": TierLevel.L0,
        "medium": TierLevel.L1,
        "expensive": TierLevel.L2,
        "premium": TierLevel.L3,
    }

    # Legacy tier name aliases for backward compat
    _TIER_ALIASES: Dict[str, str] = {
        "cheap": "L0-Coder",
        "medium": "L1-Coder",
        "expensive": "L2-Coder",
        "premium": "L3-Coder",
    }

    @classmethod
    def normalize_tier_name(cls, tier: str) -> str:
        """Normalize tier names, including legacy aliases (cheap→L0-Coder, etc.)."""
        return cls._TIER_ALIASES.get(tier.lower(), tier)

    @classmethod
    def get_default_tier(cls) -> Tier:
        tiers = cls._build_tiers()
        return tiers[0] if tiers else None

    @classmethod
    def get_max_tier(cls) -> Tier:
        tiers = cls._build_tiers()
        return tiers[-1] if tiers else None

    def __init__(self, budget_config: Optional[BudgetTierConfig] = None):
        self.budget_config = budget_config or BudgetTierConfig()

    def find_capable_model(self, tier_level: TierLevel, token_count: int = 0, requires_tools: bool = False) -> str | None:
        tiers = self._build_tiers()
        current_index = next((i for i, t in enumerate(tiers) if t.level == tier_level), 0)

        for i in range(current_index, len(tiers)):
            tier = tiers[i]
            if tier.model == "<principal-agent>":
                continue
            capability = MODEL_REGISTRY.get(tier.model)
            if capability is not None:
                if token_count > 0 and not capability.can_handle_context(token_count):
                    continue
                if not capability.can_handle_task(requires_tools=requires_tools):
                    continue
                return tier.model
            # No capability data — assume capable
            return tier.model

        return None

    def select_tier(self, task_complexity: str = "medium", budget_remaining_percent: Decimal = Decimal("1.0"),
                    force_tier: Optional[TierLevel] = None) -> tuple[Tier, bool, str]:
        if force_tier:
            tier = self.get_tier(force_tier)
            return (tier, False, f"Force tier requested: {force_tier.value}")

        should_restrict, preferred_tier = self.budget_config.should_restrict_tier(
            task_complexity, budget_remaining_percent
        )

        if should_restrict:
            selected_tier = self.get_tier(TierLevel.L0)
            reason = f"Budget restriction: selecting L0"
            was_restricted = True
        else:
            selected_tier = self.get_tier(preferred_tier)
            was_restricted = False
            reason = f"Budget-aware selection at {budget_remaining_percent*100:.0f}% remaining: {preferred_tier.value}"

        if self.budget_config.log_budget_decisions:
            logger.info(f"[TIER SELECTED] {reason} | Task: {task_complexity} | Budget: {budget_remaining_percent*100:.1f}%")

        return (selected_tier, was_restricted, reason)

    def get_budget_aware_status(self, budget_remaining_percent: Decimal) -> Dict:
        preferred_tier = self.budget_config.get_preferred_tier(budget_remaining_percent)
        return {
            "budget_remaining_percent": float(budget_remaining_percent),
            "preferred_tier": preferred_tier.value,
            "enable_budget_awareness": self.budget_config.enable_budget_awareness,
            "budget_tier_thresholds": {str(k): v.value for k, v in self.budget_config.budget_tier_thresholds.items()},
        }
