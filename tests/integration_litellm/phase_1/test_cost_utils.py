"""Phase 1: Cost calculation utility tests."""

import pytest
from decimal import Decimal
from src.adapters.cost_calculator import CostCalculator, CostEstimate, PricingTier


@pytest.fixture
def calculator():
    """Create a CostCalculator with default pricing."""
    return CostCalculator()


@pytest.fixture
def calculator_with_pricing_file():
    """Create a CostCalculator that loads the provider_pricing.toml."""
    import os
    pricing_path = os.path.join(
        os.path.dirname(__file__), 
        "../../../src/adapters/provider_pricing.toml"
    )
    return CostCalculator(pricing_file=os.path.abspath(pricing_path))


class TestCostEstimate:
    """CostEstimate dataclass tests."""
    
    def test_cost_estimate_defaults(self):
        est = CostEstimate()
        assert est.min_cost == Decimal("0")
        assert est.max_cost == Decimal("0")
        assert est.total_tokens == 0
    
    def test_cost_estimate_tokens(self):
        est = CostEstimate(input_tokens=100, output_tokens=50)
        assert est.total_tokens == 150


class TestCostCalculator:
    """Core calculator tests."""
    
    def test_get_pricing_known_model(self, calculator):
        pricing = calculator.get_pricing("openai", "gpt-4o")
        assert pricing.provider == "openai"
        assert pricing.model == "gpt-4o"
        assert pricing.input_per_1k > 0
        assert pricing.output_per_1k > 0
    
    def test_get_pricing_unknown_model_returns_median(self, calculator):
        pricing = calculator.get_pricing("unknown", "unknown-model")
        assert pricing.source == "median_guess"
        assert pricing.input_per_1k > 0
    
    def test_get_pricing_default_provider(self, calculator):
        """Providers with __default__ pricing use it for unknown models."""
        pricing = calculator.get_pricing("lmstudio", "any-model")
        assert pricing.input_per_1k == Decimal("0")  # local = free
    
    def test_estimate_cost_openai(self, calculator):
        """Test minimum cost (input-only) and expected cost."""
        est = calculator.estimate_cost("openai", "gpt-4o", input_tokens=1000, output_tokens=500)
        # min_cost: input only = 1000/1000 * 0.00250 = 0.00250
        # expected_cost: uses output_tokens = 0.00750 total
        assert est.min_cost == Decimal("0.002500")
        assert est.max_cost == Decimal("0.007500")
        assert est.expected_cost == Decimal("0.007500")
        assert est.expected_cost > Decimal("0")
    
    def test_estimate_cost_zero_tokens(self, calculator):
        """Pre-request estimate with no token counts."""
        est = calculator.estimate_cost("openai", "gpt-4o-mini")
        assert est.min_cost >= Decimal("0")
        assert est.expected_cost > Decimal("0")  # Uses estimated output
    
    def test_estimate_cost_with_estimated_output(self, calculator):
        est = calculator.estimate_cost("openai", "gpt-4o", 
                                       input_tokens=100, estimated_output_tokens=200)
        assert est.output_tokens == 200
        assert est.expected_cost > est.min_cost
    
    def test_calculate_actual_cost(self, calculator):
        cost = calculator.calculate_actual_cost("openai", "gpt-4o", 1000, 500)
        # 1000/1000*0.00250 + 500/1000*0.01000 = 0.00250 + 0.00500 = 0.00750
        assert cost == Decimal("0.007500")
    
    def test_can_afford_true(self, calculator):
        assert calculator.can_afford("openai", "gpt-4o-mini", 100, 10.00) is True
    
    def test_can_afford_false(self, calculator):
        # gpt-4o with 1M tokens would cost ~$10 — way over $0.01 budget
        assert calculator.can_afford("openai", "gpt-4o", 1000000, 0.01) is False
    
    def test_calculate_actual_cost_lmstudio_is_free(self, calculator):
        cost = calculator.calculate_actual_cost("lmstudio", "any-model", 10000, 5000)
        assert cost == Decimal("0.000000")
    
    def test_list_providers(self, calculator):
        providers = calculator.list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
    
    def test_list_models(self, calculator):
        models = calculator.list_models("openai")
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models
        assert "__default__" not in models  # Should filter out default entries


class TestCostCalculatorWithFile:
    """Tests using the TOML pricing file."""
    
    def test_pricing_file_loads(self, calculator_with_pricing_file):
        """Verify the TOML pricing file loads without errors."""
        pricing = calculator_with_pricing_file.get_pricing("groq", "llama-4-scout-17b-16e")
        assert pricing.input_per_1k == Decimal("0.00010")
        assert pricing.output_per_1k == Decimal("0.00030")
        assert pricing.source == "https://groq.com/pricing"
    
    def test_pricing_file_mistral(self, calculator_with_pricing_file):
        pricing = calculator_with_pricing_file.get_pricing("mistral", "mistral-small-latest")
        assert pricing.input_per_1k == Decimal("0.00100")


class TestCostCalculatorVault:
    """Tests with vault-backed pricing."""
    
    def test_vault_pricing_priority(self):
        """Vault pricing should take priority over built-in defaults."""
        vault_data = {}
        def mock_vault(path):
            return vault_data.get(path)
        
        # Set vault pricing that differs from built-in
        import json
        vault_data["/providers/openai/gpt-4o/pricing"] = json.dumps({
            "input_per_1k": "0.00100",  # Lower than built-in 0.00250
            "output_per_1k": "0.00500",
        })
        
        calc = CostCalculator(vault_getter=mock_vault)
        pricing = calc.get_pricing("openai", "gpt-4o")
        assert pricing.input_per_1k == Decimal("0.00100")  # Vault wins
        assert pricing.source == "vault"
    
    def test_vault_miss_falls_back_to_default(self):
        """When vault has no entry, fall back to built-in."""
        calc = CostCalculator(vault_getter=lambda path: None)
        pricing = calc.get_pricing("openai", "gpt-4o")
        assert pricing.input_per_1k == Decimal("0.00250")  # Built-in default


class TestCostEstimatesArePositive:
    """Edge case tests."""
    
    def test_estimate_never_negative(self, calculator):
        est = calculator.estimate_cost("openai", "gpt-4o", input_tokens=0, output_tokens=0)
        assert est.min_cost >= Decimal("0")
        assert est.expected_cost >= Decimal("0")
    
    def test_high_volume_estimate(self, calculator):
        """1M token request should still calculate correctly."""
        est = calculator.estimate_cost("openai", "gpt-4o", 
                                       input_tokens=500000, output_tokens=500000)
        assert est.min_cost > Decimal("0")
        # ~ $6.25 for 500K input + 500K output with gpt-4o pricing
        assert est.min_cost > Decimal("1.00")


class TestPricingTier:
    """PricingTier dataclass tests."""
    
    def test_pricing_tier_defaults(self):
        tier = PricingTier("test", "test-model")
        assert tier.provider == "test"
        assert tier.input_per_1k == Decimal("0")
        assert tier.currency == "USD"
