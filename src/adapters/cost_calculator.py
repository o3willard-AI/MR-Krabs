"""Unified cost calculation and provider pricing registry.

Provides accurate cost prediction and tracking across all LLM providers.
Used by SmartRouter (Phase 2) and PrometheusMetricsAdapter (Phase 1).
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional


@dataclass
class CostEstimate:
    """Estimated cost for an LLM request."""
    min_cost: Decimal = Decimal("0")
    max_cost: Decimal = Decimal("0")
    expected_cost: Decimal = Decimal("0")
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class PricingTier:
    """Pricing for a specific model."""
    provider: str
    model: str
    input_per_1k: Decimal = Decimal("0")
    output_per_1k: Decimal = Decimal("0")
    flat_fee: Decimal = Decimal("0")
    currency: str = "USD"
    source: str = ""  # URL where pricing was obtained
    last_updated: str = ""


class CostCalculator:
    """Unified cost calculation across all LLM providers.
    
    Supports per-token, per-request flat fee, and tiered volume pricing.
    Uses Decimal for sub-cent precision and accuracy.
    """
    
    # Built-in pricing defaults (overridden by pricing file and vault)
    _DEFAULT_PRICING: Dict[str, Dict[str, PricingTier]] = {
        "openai": {
            "gpt-4o": PricingTier("openai", "gpt-4o", Decimal("0.00250"), Decimal("0.01000"), source="https://openai.com/pricing"),
            "gpt-4o-mini": PricingTier("openai", "gpt-4o-mini", Decimal("0.00015"), Decimal("0.00060"), source="https://openai.com/pricing"),
            "gpt-4-turbo": PricingTier("openai", "gpt-4-turbo", Decimal("0.01000"), Decimal("0.03000"), source="https://openai.com/pricing"),
        },
        "anthropic": {
            "claude-sonnet-4-20250514": PricingTier("anthropic", "claude-sonnet-4-20250514", Decimal("0.00300"), Decimal("0.01500"), source="https://anthropic.com/pricing"),
            "claude-haiku-3-5": PricingTier("anthropic", "claude-haiku-3-5", Decimal("0.00080"), Decimal("0.00400"), source="https://anthropic.com/pricing"),
        },
        "deepseek": {
            "deepseek-chat": PricingTier("deepseek", "deepseek-chat", Decimal("0.00014"), Decimal("0.00028"), source="https://deepseek.com/pricing"),
            "deepseek-reasoner": PricingTier("deepseek", "deepseek-reasoner", Decimal("0.00055"), Decimal("0.00219"), source="https://deepseek.com/pricing"),
        },
        "openrouter": {
            "__default__": PricingTier("openrouter", "__default__", Decimal("0.000001"), Decimal("0.000001"), source="https://openrouter.ai/models"),
        },
        "lmstudio": {
            "__default__": PricingTier("lmstudio", "__default__", Decimal("0"), Decimal("0"), source="local"),
        },
    }
    
    _MEDIAN_PRICE_PER_1K: Decimal = Decimal("0.005")  # Used when model is unknown
    
    def __init__(self, pricing_file: Optional[str] = None, vault_getter=None):
        """Initialize cost calculator.
        
        Args:
            pricing_file: Path to provider_pricing.toml for custom pricing.
            vault_getter: Optional callable(path) -> str for vault-backed pricing.
        """
        self._pricing: Dict[str, Dict[str, PricingTier]] = {}
        self._vault_getter = vault_getter
        
        # Load built-in defaults
        for provider, models in self._DEFAULT_PRICING.items():
            self._pricing[provider] = dict(models)
        
        # Load custom pricing file if provided
        if pricing_file:
            self._load_pricing_file(pricing_file)
    
    def _load_pricing_file(self, path: str) -> None:
        """Load provider pricing from a TOML file."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            for provider, models in data.get("providers", {}).items():
                if provider not in self._pricing:
                    self._pricing[provider] = {}
                for model, pricing in models.items():
                    self._pricing[provider][model] = PricingTier(
                        provider=provider,
                        model=model,
                        input_per_1k=Decimal(str(pricing.get("input_per_1k", 0))),
                        output_per_1k=Decimal(str(pricing.get("output_per_1k", 0))),
                        flat_fee=Decimal(str(pricing.get("flat_fee", 0))),
                        source=pricing.get("source", "pricing_file"),
                        last_updated=pricing.get("last_updated", ""),
                    )
        except FileNotFoundError:
            pass  # Pricing file is optional
    
    def get_pricing(self, provider: str, model: str) -> PricingTier:
        """Get pricing for a specific provider+model.
        
        Priority: vault → pricing file → built-in defaults → median guess
        """
        # Try vault first
        if self._vault_getter:
            try:
                vault_data = self._vault_getter(f"/providers/{provider}/{model}/pricing")
                if vault_data:
                    # Vault returns JSON; parse into PricingTier
                    import json
                    data = json.loads(vault_data)
                    return PricingTier(
                        provider=provider, model=model,
                        input_per_1k=Decimal(str(data.get("input_per_1k", "0"))),
                        output_per_1k=Decimal(str(data.get("output_per_1k", "0"))),
                        source="vault",
                    )
            except Exception:
                pass  # Vault miss or parse error → fall through
        
        # Try pricing registry
        if provider in self._pricing:
            if model in self._pricing[provider]:
                return self._pricing[provider][model]
            if "__default__" in self._pricing[provider]:
                return self._pricing[provider]["__default__"]
        
        # Median guess
        return PricingTier(
            provider=provider, model=model,
            input_per_1k=self._MEDIAN_PRICE_PER_1K,
            output_per_1k=self._MEDIAN_PRICE_PER_1K,
            source="median_guess",
        )
    
    def estimate_cost(self, provider: str, model: str, 
                      input_tokens: int = 0, output_tokens: int = 0,
                      estimated_output_tokens: Optional[int] = None) -> CostEstimate:
        """Estimate cost for a request.
        
        Args:
            provider: LLM provider name.
            model: Model identifier.
            input_tokens: Known input token count (can be 0 for pre-request estimation).
            output_tokens: Expected output token count (0 for pre-request).
            estimated_output_tokens: Override for pre-request estimation.
        """
        pricing = self.get_pricing(provider, model)
        
        output = output_tokens or estimated_output_tokens or 0
        
        min_cost = (Decimal(input_tokens) / 1000 * pricing.input_per_1k + 
                   Decimal(0) / 1000 * pricing.output_per_1k + pricing.flat_fee)
        
        max_cost = (Decimal(input_tokens) / 1000 * pricing.input_per_1k + 
                   Decimal(output or 4096) / 1000 * pricing.output_per_1k + pricing.flat_fee)
        
        # Expected: assume 1:1 input:output ratio for estimation
        expected_output = output or max(input_tokens, 100)
        expected_cost = (Decimal(input_tokens) / 1000 * pricing.input_per_1k + 
                        Decimal(expected_output) / 1000 * pricing.output_per_1k + pricing.flat_fee)
        
        return CostEstimate(
            min_cost=min_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            max_cost=max_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            expected_cost=expected_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output or expected_output,
        )
    
    def calculate_actual_cost(self, provider: str, model: str,
                               input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate actual cost from real token usage."""
        pricing = self.get_pricing(provider, model)
        cost = (Decimal(input_tokens) / 1000 * pricing.input_per_1k +
               Decimal(output_tokens) / 1000 * pricing.output_per_1k +
               pricing.flat_fee)
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    
    def can_afford(self, provider: str, model: str, 
                   input_tokens: int, budget_remaining: float,
                   estimated_output_tokens: Optional[int] = None) -> bool:
        """Check if estimated cost fits within remaining budget."""
        estimate = self.estimate_cost(provider, model, input_tokens,
                                      estimated_output_tokens=estimated_output_tokens)
        return estimate.min_cost <= Decimal(str(budget_remaining))
    
    def list_providers(self) -> list[str]:
        """List all providers with pricing data."""
        return list(self._pricing.keys())
    
    def list_models(self, provider: str) -> list[str]:
        """List all models for a provider."""
        if provider not in self._pricing:
            return []
        return [m for m in self._pricing[provider] if m != "__default__"]
