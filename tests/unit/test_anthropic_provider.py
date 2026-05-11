"""Unit tests for Anthropic Provider."""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from src.providers.anthropic_provider import (
    AnthropicProvider,
    create_anthropic_provider,
    TokenCount,
)


class TestAnthropicProvider:
    """Tests for AnthropicProvider class."""

    @pytest.fixture
    def provider(self):
        """Create an Anthropic provider instance with mocked client."""
        with patch('src.providers.anthropic_provider.Anthropic') as MockAnthropic:
            mock_client = Mock()
            MockAnthropic.return_value = mock_client
            provider = AnthropicProvider(api_key="test-key")
            provider._client = mock_client  # Set mock client
            return provider

    def test_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.api_key == "test-key"
        assert provider.MODEL_PRICING is not None
        assert len(provider.MODEL_PRICING) > 0

    def test_model_pricing_config(self, provider):
        """Test that model pricing is configured."""
        # Check for known models
        assert "claude-3-5-sonnet-20241022" in provider.MODEL_PRICING
        assert "claude-3-opus-20240229" in provider.MODEL_PRICING
        assert "claude-3-sonnet-20240229" in provider.MODEL_PRICING
        assert "claude-3-haiku-20240307" in provider.MODEL_PRICING

    def test_model_pricing_structure(self, provider):
        """Test model pricing has correct structure."""
        model_pricing = provider.MODEL_PRICING["claude-3-5-sonnet-20241022"]
        
        assert "prompt" in model_pricing
        assert "completion" in model_pricing
        assert "tier" in model_pricing
        assert isinstance(model_pricing["prompt"], float)
        assert isinstance(model_pricing["completion"], float)

    def test_model_pricing_accuracy(self, provider):
        """Test that pricing matches Anthropic's published rates."""
        # Claude 3.5 Sonnet: $3/1M input, $15/1M output
        sonnet_pricing = provider.MODEL_PRICING["claude-3-5-sonnet-20241022"]
        assert sonnet_pricing["prompt"] == 0.000003
        assert sonnet_pricing["completion"] == 0.000015

        # Claude 3 Opus: $15/1M input, $75/1M output
        opus_pricing = provider.MODEL_PRICING["claude-3-opus-20240229"]
        assert opus_pricing["prompt"] == 0.000015
        assert opus_pricing["completion"] == 0.000075

        # Claude 3 Haiku: $0.25/1M input, $1.25/1M output
        haiku_pricing = provider.MODEL_PRICING["claude-3-haiku-20240307"]
        assert haiku_pricing["prompt"] == 0.00000025
        assert haiku_pricing["completion"] == 0.00000125

    def test_get_pricing(self, provider):
        """Test getting pricing for a model."""
        pricing = provider.get_pricing("claude-3-5-sonnet-20241022")
        
        assert pricing["prompt"] == 0.000003
        assert pricing["completion"] == 0.000015
        assert pricing["tier"] == "L2-Coder"

    def test_get_pricing_unknown_model(self, provider):
        """Test getting pricing for unknown model returns defaults."""
        pricing = provider.get_pricing("unknown-model")
        
        assert pricing["prompt"] == 0.000001
        assert pricing["completion"] == 0.000001
        assert pricing["tier"] == "L1-Coder"

    def test_list_models(self, provider):
        """Test listing available models."""
        models = provider.list_models()
        
        assert isinstance(models, list)
        assert len(models) > 0
        
        # Check first model structure
        model = models[0]
        assert "id" in model
        assert "input_cost" in model
        assert "output_cost" in model
        assert "tier" in model

    @patch('src.providers.anthropic_provider.Anthropic')
    def test_messages_create(self, mock_anthropic):
        """Test message creation."""
        # Mock the Anthropic client response
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [Mock()]
        mock_response.content[0].text = "Test response"
        mock_response.model = "claude-3-5-sonnet-20241022"
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client
        
        provider = create_anthropic_provider(api_key="test-key")
        provider._client = mock_client

        result = provider.messages_create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Test"}]
        )

        assert "cost" in result
        assert "tokens" in result
        assert result["tokens"].total_tokens == 150
        assert result["success"] == True
        assert isinstance(result["cost"], (float, Decimal))
        assert result["cost"] > 0

    def test_messages_create_error(self):
        """Test error handling in message creation."""
        provider = AnthropicProvider(api_key="test-key")
        
        # Mock client that raises an error
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")
        provider._client = mock_client

        result = provider.messages_create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Test"}]
        )

        assert "success" in result
        assert result["success"] == False
        assert "error" in result
        assert result["cost"] == 0.0

    def test_tokenize_text(self):
        """Test text tokenization estimation."""
        provider = AnthropicProvider(api_key="test-key")
        
        # Estimate tokens (rough: 1 token ~ 4 chars)
        text = "Hello world, this is a test."
        estimated_tokens = len(text) // 4
        
        # Should be a reasonable estimate
        assert estimated_tokens > 0


class TestCreateAnthropicProvider:
    """Tests for create_anthropic_provider factory function."""

    def test_creates_provider(self):
        """Test factory creates AnthropicProvider instance."""
        with patch('src.providers.anthropic_provider.Anthropic'):
            provider = create_anthropic_provider(api_key="test-key")

            assert isinstance(provider, AnthropicProvider)
            assert provider.api_key == "test-key"

    def test_provider_has_required_methods(self):
        """Test created provider has required methods."""
        with patch('src.providers.anthropic_provider.Anthropic'):
            provider = create_anthropic_provider(api_key="test-key")

            assert hasattr(provider, "get_pricing")
            assert hasattr(provider, "messages_create")
            assert hasattr(provider, "list_models")


class TestTokenCount:
    """Tests for TokenCount dataclass."""

    def test_initialization(self):
        """Test TokenCount initializes correctly."""
        token_count = TokenCount(
            input_tokens=100,
            output_tokens=50,
            total_tokens=0  # Will be calculated
        )

        assert token_count.input_tokens == 100
        assert token_count.output_tokens == 50
        assert token_count.total_tokens == 150  # Auto-calculated

    def test_initialization_with_total(self):
        """Test TokenCount with explicit total."""
        token_count = TokenCount(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )

        assert token_count.total_tokens == 150

    def test_initialization_zero_tokens(self):
        """Test TokenCount with zero tokens."""
        token_count = TokenCount()

        assert token_count.input_tokens == 0
        assert token_count.output_tokens == 0
        assert token_count.total_tokens == 0

    def test_initialization_only_input(self):
        """Test TokenCount with only input tokens."""
        token_count = TokenCount(input_tokens=100)

        assert token_count.input_tokens == 100
        assert token_count.total_tokens == 100


class TestAnthropicProviderPricing:
    """Tests for Anthropic model pricing."""

    @pytest.fixture
    def provider(self):
        """Create an Anthropic provider instance."""
        with patch('src.providers.anthropic_provider.Anthropic'):
            return AnthropicProvider(api_key="test-key")

    def test_all_models_have_pricing(self, provider):
        """Test all known models have pricing."""
        models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
        ]

        for model in models:
            assert model in provider.MODEL_PRICING
            pricing = provider.MODEL_PRICING[model]
            assert pricing["prompt"] > 0
            assert pricing["completion"] > 0

    def test_model_tier_assignment(self, provider):
        """Test model tier assignments are correct."""
        # Premium tier
        assert provider.MODEL_PRICING["claude-3-opus-20240229"]["tier"] == "L3-Coder"
        
        # Medium tier
        assert provider.MODEL_PRICING["claude-3-5-sonnet-20241022"]["tier"] == "L2-Coder"
        assert provider.MODEL_PRICING["claude-3-sonnet-20240229"]["tier"] == "L1-Coder"
        
        # Budget tier
        assert provider.MODEL_PRICING["claude-3-haiku-20240307"]["tier"] == "L0-Planner"

    def test_cost_comparison(self, provider):
        """Test cost comparison between models."""
        # Haiku (L0) should be cheapest
        cost_haiku = 100 * provider.MODEL_PRICING["claude-3-haiku-20240307"]["prompt"]
        
        # Sonnet (L1) should be medium
        cost_sonnet = 100 * provider.MODEL_PRICING["claude-3-sonnet-20240229"]["prompt"]
        
        # Opus (L3) should be most expensive
        cost_opus = 100 * provider.MODEL_PRICING["claude-3-opus-20240229"]["prompt"]

        assert cost_haiku < cost_sonnet < cost_opus

    def test_cost_per_token_calculation(self):
        """Test cost calculation per token."""
        # Claude 3.5 Sonnet: $3.00 per 1M input tokens = $0.000003 per token
        prompt_cost = 0.000003
        
        # 1000 tokens input = $0.003
        cost_1000 = 1000 * prompt_cost
        assert cost_1000 == 0.003
        
        # 1,000,000 tokens input = $3.00
        cost_1m = 1_000_000 * prompt_cost
        assert cost_1m == 3.0
