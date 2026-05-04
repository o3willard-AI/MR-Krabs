"""Unit tests for OpenAI Provider."""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from src.providers.openai_provider import (
    OpenAIProvider,
    create_openai_provider,
    TokenCount,
)


class TestOpenAIProvider:
    """Tests for OpenAIProvider class."""

    @pytest.fixture
    def provider(self):
        """Create an OpenAI provider instance with mocked client."""
        with patch('src.providers.openai_provider.OpenAI') as MockOpenAI:
            mock_client = Mock()
            MockOpenAI.return_value = mock_client
            provider = OpenAIProvider(api_key="test-key")
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
        assert "gpt-4o" in provider.MODEL_PRICING
        assert "gpt-4" in provider.MODEL_PRICING
        assert "gpt-3.5-turbo" in provider.MODEL_PRICING

    def test_model_pricing_structure(self, provider):
        """Test model pricing has correct structure."""
        model_pricing = provider.MODEL_PRICING["gpt-4o"]
        
        assert "prompt" in model_pricing
        assert "completion" in model_pricing
        assert "tier" in model_pricing
        assert isinstance(model_pricing["prompt"], float)
        assert isinstance(model_pricing["completion"], float)

    def test_model_pricing_per_token(self, provider):
        """Test that pricing is per token (not per 1K)."""
        # GPT-4o: $0.0000025 per token (from 1K pricing)
        pricing = provider.MODEL_PRICING["gpt-4o"]
        
        assert pricing["prompt"] == 0.0000025
        assert pricing["completion"] == 0.000010

    def test_get_pricing(self, provider):
        """Test getting pricing for a model."""
        pricing = provider.get_pricing("gpt-4o")
        
        assert pricing["prompt"] == 0.0000025
        assert pricing["completion"] == 0.000010
        assert pricing["tier"] == "L3-Coder"

    def test_get_pricing_unknown_model(self, provider):
        """Test getting pricing for unknown model returns defaults."""
        pricing = provider.get_pricing("unknown-model")
        
        assert pricing["prompt"] == 0.000001
        assert pricing["completion"] == 0.000001
        assert pricing["tier"] == "L1-Coder"

    def test_get_pricing_partial_match(self, provider):
        """Test partial matching for model names."""
        # Should match gpt-3.5-turbo
        pricing = provider.get_pricing("gpt-3.5-turbo-0125")
        
        assert pricing["prompt"] == 0.0000005
        assert pricing["tier"] == "L0-Planner"

    def test_list_models(self, provider):
        """Test listing available models."""
        models = provider.list_models()
        
        assert isinstance(models, list)
        assert len(models) > 0
        
        # Check first model structure
        model = models[0]
        assert "id" in model
        assert "prompt_cost" in model
        assert "completion_cost" in model
        assert "tier" in model

    @patch('src.providers.openai_provider.OpenAI')
    def test_chat_completions_create(self, mock_openai):
        """Test chat completions creation."""
        # Mock the OpenAI client response
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.model = "gpt-4o"
        mock_response.response_ms = 1000
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        provider = create_openai_provider(api_key="test-key")
        provider._client = mock_client

        result = provider.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}]
        )

        assert "cost" in result
        assert "tokens" in result
        assert result["tokens"].total_tokens == 150
        assert result["success"] == True
        assert isinstance(result["cost"], float)
        assert result["cost"] > 0

    def test_chat_completions_create_error(self):
        """Test error handling in chat completions."""
        provider = OpenAIProvider(api_key="test-key")
        
        # Mock client that raises an error
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        provider._client = mock_client

        result = provider.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}]
        )

        assert "success" in result
        assert result["success"] == False
        assert "error" in result
        assert result["cost"] == 0.0

    @patch('src.providers.openai_provider.OpenAI')
    def test_embeddings_create(self, mock_openai):
        """Test embeddings creation."""
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_embedding = Mock()
        mock_embedding.embedding = [0.1] * 1536
        mock_response.data = [mock_embedding, mock_embedding]
        
        mock_client = Mock()
        mock_client.embeddings.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        provider = create_openai_provider(api_key="test-key")
        provider._client = mock_client

        result = provider.embeddings_create(
            model="text-embedding-ada-002",
            input=["Test text", "Another text"]
        )

        assert "cost" in result
        assert "embeddings" in result
        assert len(result["embeddings"]) == 2
        assert len(result["embeddings"][0]) == 1536
        assert result["success"] == True

    def test_embeddings_create_string_input(self):
        """Test embeddings with string input."""
        with patch('src.providers.openai_provider.OpenAI') as MockOpenAI:
            # Mock client
            mock_client = Mock()
            mock_embedding = Mock()
            mock_embedding.embedding = [0.1] * 1536
            mock_response = Mock()
            mock_response.data = [mock_embedding]
            mock_client.embeddings.create.return_value = mock_response
            MockOpenAI.return_value = mock_client
            
            provider = create_openai_provider(api_key="test-key")
            provider._client = mock_client

            result = provider.embeddings_create(
                model="text-embedding-3-small",
                input="Single text input"
            )

            assert "embeddings" in result
            assert len(result["embeddings"]) == 1


class TestCreateOpenAIProvider:
    """Tests for create_openai_provider factory function."""

    def test_creates_provider(self):
        """Test factory creates OpenAIProvider instance."""
        with patch('src.providers.openai_provider.OpenAI'):
            provider = create_openai_provider(api_key="test-key")

            assert isinstance(provider, OpenAIProvider)
            assert provider.api_key == "test-key"

    def test_provider_has_required_methods(self):
        """Test created provider has required methods."""
        with patch('src.providers.openai_provider.OpenAI'):
            provider = create_openai_provider(api_key="test-key")

            assert hasattr(provider, "get_pricing")
            assert hasattr(provider, "chat_completions_create")
            assert hasattr(provider, "embeddings_create")
            assert hasattr(provider, "list_models")


class TestTokenCount:
    """Tests for TokenCount dataclass."""

    def test_initialization(self):
        """Test TokenCount initializes correctly."""
        token_count = TokenCount(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=0  # Will be calculated
        )

        assert token_count.prompt_tokens == 100
        assert token_count.completion_tokens == 50
        assert token_count.total_tokens == 150  # Auto-calculated

    def test_initialization_with_total(self):
        """Test TokenCount with explicit total."""
        token_count = TokenCount(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )

        assert token_count.total_tokens == 150

    def test_initialization_zero_tokens(self):
        """Test TokenCount with zero tokens."""
        token_count = TokenCount()

        assert token_count.prompt_tokens == 0
        assert token_count.completion_tokens == 0
        assert token_count.total_tokens == 0

    def test_initialization_only_prompt(self):
        """Test TokenCount with only prompt tokens."""
        token_count = TokenCount(prompt_tokens=100)

        assert token_count.prompt_tokens == 100
        assert token_count.total_tokens == 100


class TestOpenAIProviderPricing:
    """Tests for OpenAI model pricing."""

    @pytest.fixture
    def provider(self):
        """Create an OpenAI provider instance."""
        with patch('src.providers.openai_provider.OpenAI'):
            return OpenAIProvider(api_key="test-key")

    def test_all_models_have_pricing(self, provider):
        """Test all known models have pricing."""
        models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "gpt-3.5-turbo-0125",
        ]

        for model in models:
            assert model in provider.MODEL_PRICING
            pricing = provider.MODEL_PRICING[model]
            assert pricing["prompt"] > 0
            assert pricing["completion"] > 0

    def test_model_tier_assignment(self, provider):
        """Test model tier assignments are correct."""
        # Premium tier
        assert provider.MODEL_PRICING["gpt-4o"]["tier"] == "L3-Coder"
        assert provider.MODEL_PRICING["gpt-4-turbo"]["tier"] == "L3-Coder"
        assert provider.MODEL_PRICING["gpt-4"]["tier"] == "L3-Coder"
        
        # Budget tier
        assert provider.MODEL_PRICING["gpt-3.5-turbo"]["tier"] == "L0-Planner"
        assert provider.MODEL_PRICING["gpt-3.5-turbo-16k"]["tier"] == "L0-Planner"
        assert provider.MODEL_PRICING["gpt-4o-mini"]["tier"] == "L1-Coder"

    def test_cost_per_token_calculation(self):
        """Test cost calculation per token."""
        # GPT-4o: $2.50 per 1M input tokens = $0.0000025 per token
        prompt_cost = 0.0000025
        completion_cost = 0.000010
        
        # 1000 tokens input = $0.0025
        cost_1000 = 1000 * prompt_cost
        assert cost_1000 == 0.0025
        
        # 1,000,000 tokens input = $2.50
        cost_1m = 1_000_000 * prompt_cost
        assert cost_1m == 2.5
