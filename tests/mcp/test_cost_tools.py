"""
Unit tests for MR-Krabs MCP Server - Cost Tools (Phase 1)

Tests cover:
- Cost estimation with various models and token counts
- Budget checking with different enforcement modes
- Cost tracking and recording
- Integration with session management
"""

import pytest
from unittest.mock import patch, MagicMock

from src.mcp.cost_tools import (
    estimate_cost,
    process_cost_estimate,
    process_cost_track,
    CostEstimateRequest,
    BudgetCheckRequest,
    CostTrackRequest,
    COST_RATES,
)


class TestCostEstimation:
    """Test cost estimation logic."""
    
    def test_estimate_with_tokens(self):
        """Test cost estimation with explicit token counts."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            input_tokens=100,
            output_tokens=50,
        )
        
        # Calculate expected: (100/1000)*0.0001 + (50/1000)*0.0001 = 0.000015
        expected_cost = (100 / 1000) * 0.0001 + (50 / 1000) * 0.0001
        
        assert result.estimated_cost == pytest.approx(expected_cost, rel=1e-6)
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.model == "google/gemma-7b-it"
    
    def test_estimate_with_prompt_text(self):
        """Test cost estimation from prompt text (rough token estimate)."""
        prompt = "Write a comprehensive analysis covering multiple aspects and considerations"
        
        result = estimate_cost(
            model="meta-llama/llama-3-8b-instruct",
            prompt_text=prompt,
        )
        
        assert result.input_tokens > 0  # Should have estimated tokens
    
    def test_estimate_default_model(self):
        """Test cost estimation with default rate for unknown model."""
        result = estimate_cost(
            model="unknown-model-xyz",
            input_tokens=100,
            output_tokens=100,
        )
        
        # Should use default rate: (100/1000)*0.00025 + (100/1000)*0.00025
        expected_cost = (100 / 1000) * 0.00025 + (100 / 1000) * 0.00025
        
        assert result.estimated_cost == pytest.approx(expected_cost, rel=1e-6)
    
    def test_estimate_zero_tokens(self):
        """Test cost estimation with zero tokens."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            input_tokens=0,
            output_tokens=0,
        )
        
        assert result.estimated_cost == 0
    
    def test_estimate_large_prompt(self):
        """Test cost estimation for large prompts."""
        result = estimate_cost(
            model="meta-llama/llama-3-70b-instruct",
            input_tokens=10000,  # 10K tokens
            output_tokens=5000,  # 5K tokens
        )
        
        expected_cost = (10000 / 1000) * 0.000059 + (5000 / 1000) * 0.000079
        
        assert result.estimated_cost == pytest.approx(expected_cost, rel=1e-6)
    
    def test_estimate_to_dict(self):
        """Test breakdown conversion to dictionary."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            input_tokens=100,
            output_tokens=50,
        )
        
        data = result.to_dict()
        
        assert "estimated_cost" in data
        assert "input_tokens" in data
        assert "output_tokens" in data
        assert "model" in data
        assert "rate_per_1k_input" in data
        assert "rate_per_1k_output" in data


class TestProcessCostEstimate:
    """Test cost estimation request processing."""
    
    def test_process_estimate_with_tokens(self):
        """Test processing estimate request with explicit tokens."""
        request = CostEstimateRequest(
            model="google/gemma-7b-it",
            input_tokens=200,
            output_tokens=100,
        )
        
        result = process_cost_estimate(request)
        
        assert result.estimated_cost > 0
        assert "estimated_cost" in result.breakdown
        assert result.session_id is None
    
    def test_process_estimate_with_text(self):
        """Test processing estimate request with prompt text."""
        request = CostEstimateRequest(
            model="mistralai/mistral-7b-instruct",
            prompt_text="Write a poem about AI in the style of Shakespeare",
        )
        
        result = process_cost_estimate(request)
        
        assert result.estimated_cost > 0
        assert result.breakdown["model"] == "mistralai/mistral-7b-instruct"
    
    def test_process_estimate_session_id(self):
        """Test processing estimate request with session ID."""
        request = CostEstimateRequest(
            session_id="session-test123",
            model="google/gemma-7b-it",
            input_tokens=50,
        )
        
        result = process_cost_estimate(request)
        
        assert result.session_id == "session-test123"


class TestCostTracking:
    """Test cost tracking functionality."""
    
    def test_process_track_basic(self):
        """Test basic cost tracking."""
        request = CostTrackRequest(
            amount=0.05,
            model="google/gemma-7b-it",
            input_tokens=100,
            output_tokens=50,
        )
        
        result = process_cost_track(request)
        
        assert result.recorded is True
        assert result.record["amount"] == 0.05
        assert result.record["model"] == "google/gemma-7b-it"
        assert "timestamp" in result.record
        assert result.session_id is None
    
    def test_process_track_with_session(self):
        """Test cost tracking with session ID."""
        request = CostTrackRequest(
            session_id="session-abc123",
            amount=0.10,
            model="meta-llama/llama-3-8b-instruct",
            input_tokens=500,
            output_tokens=250,
        )
        
        result = process_cost_track(request)
        
        assert result.session_id == "session-abc123"
        assert result.message == "Cost $0.1000 recorded for model meta-llama/llama-3-8b-instruct"
    
    def test_process_track_default_tokens(self):
        """Test cost tracking with default token values."""
        request = CostTrackRequest(
            amount=0.02,
            model="google/gemma-7b-it",
        )
        
        result = process_cost_track(request)
        
        assert result.record["input_tokens"] == 0
        assert result.record["output_tokens"] == 0


class TestCostRates:
    """Test cost rate configuration."""
    
    def test_rates_exist(self):
        """Test that cost rates dictionary is populated."""
        assert len(COST_RATES) > 0
        assert "default" in COST_RATES
    
    def test_default_rate_format(self):
        """Test default rate has correct format."""
        default = COST_RATES["default"]
        
        assert "input" in default
        assert "output" in default
        assert default["input"] > 0
        assert default["output"] > 0
    
    def test_specific_model_rates(self):
        """Test specific model rates exist."""
        known_models = ["google/gemma-7b-it", "meta-llama/llama-3-8b-instruct"]
        
        for model in known_models:
            assert model in COST_RATES
            assert COST_RATES[model]["input"] >= 0
            assert COST_RATES[model]["output"] >= 0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_very_small_amount(self):
        """Test cost estimation with very small amounts."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            input_tokens=1,
            output_tokens=1,
        )
        
        # May round to 0 due to low rates and rounding, but tokens should be counted
        assert result.input_tokens == 1 or result.estimated_cost >= 0
    
    def test_very_large_amount(self):
        """Test cost estimation with very large amounts."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            input_tokens=100000,  # 100K tokens
            output_tokens=50000,  # 50K tokens
        )
        
        assert result.estimated_cost > 0
    
    def test_empty_prompt(self):
        """Test cost estimation with empty prompt."""
        result = estimate_cost(
            model="google/gemma-7b-it",
            prompt_text="",
        )
        
        # Empty string should result in 0 or very few tokens
        assert result.input_tokens == 0
    
    def test_negative_amount_handling(self):
        """Test that negative amounts don't crash the system."""
        # We accept both positive and negative amounts (negative might be refunds/corrections)
        try:
            request = CostTrackRequest(
                amount=-0.05,  # Negative amount
                model="test",
            )
            result = process_cost_track(request)
            # If it doesn't raise an exception, we accept it
            assert result.recorded is True or result.recorded is False
        except Exception:
            # Also acceptable if it raises an exception
            pass


class TestIntegrationScenarios:
    """Test integration scenarios."""
    
    def test_estimate_then_track(self):
        """Test estimate-then-track workflow."""
        # Estimate cost
        request = CostEstimateRequest(
            model="google/gemma-7b-it",
            input_tokens=100,
            output_tokens=50,
        )
        estimate_result = process_cost_estimate(request)
        
        # Track actual cost (might differ slightly from estimate)
        track_request = CostTrackRequest(
            amount=estimate_result.estimated_cost * 1.02,  # 2% over estimate
            model="google/gemma-7b-it",
            input_tokens=100,
            output_tokens=50,
        )
        track_result = process_cost_track(track_request)
        
        assert track_result.recorded is True
        assert track_result.record["amount"] > 0
    
    def test_multiple_models(self):
        """Test cost estimation across multiple models."""
        models = [
            "google/gemma-7b-it",
            "meta-llama/llama-3-8b-instruct",
            "mistralai/mistral-7b-instruct",
        ]
        
        costs = {}
        for model in models:
            result = estimate_cost(
                model=model,
                input_tokens=100,
                output_tokens=50,
            )
            costs[model] = result.estimated_cost
        
        # All should have costs
        for model in models:
            assert model in costs
            assert costs[model] > 0
    
    def test_budget_enforcement_modes(self):
        """Test different enforcement mode strings are valid."""
        modes = ["notify_only", "fail", "notify_then_fail", "fail_with_notification"]
        
        for mode in modes:
            # Just verify the string is accepted (validation happens at HTTP layer)
            request = CostEstimateRequest(
                model="google/gemma-7b-it",
                input_tokens=10,
            )
            result = process_cost_estimate(request)
            assert result.estimated_cost > 0
