"""Phase 4: Provider adapter framework tests."""

import pytest
from decimal import Decimal
from src.adapters.providers.base_provider import (
    BaseProviderAdapter, OpenAICompatibleAdapter,
    LLMResponse, ModelInfo, CostEstimate,
)


class TestLLMResponse:
    def test_defaults(self):
        r = LLMResponse(content="hello", model="test")
        assert r.content == "hello"
        assert r.tokens_used == 0
        assert r.finish_reason == "stop"


class TestModelInfo:
    def test_defaults(self):
        m = ModelInfo(name="gpt-4o")
        assert m.name == "gpt-4o"
        assert m.context_window == 4096
        assert m.status == "available"
    
    def test_custom(self):
        m = ModelInfo(name="claude", context_window=200000, max_output_tokens=4096)
        assert m.context_window == 200000


class TestCostEstimate:
    def test_defaults(self):
        c = CostEstimate()
        assert c.min_cost == Decimal("0")


class TestOpenAICompatibleAdapter:
    """Test the OpenAI-compatible base adapter."""
    
    @pytest.fixture
    def adapter(self):
        class TestAdapter(OpenAICompatibleAdapter):
            provider_name = "test"
            default_model = "test-model"
            env_var = "TEST_API_KEY"
            base_url = "https://api.test.com/v1"
        return TestAdapter()
    
    def test_provider_metadata(self, adapter):
        assert adapter.provider_name == "test"
        assert adapter.default_model == "test-model"
    
    def test_list_models(self, adapter):
        models = adapter.list_models()
        assert len(models) >= 1
        assert models[0].name == "test-model"
    
    def test_validate_config(self, adapter):
        assert adapter.validate_config() is True
    
    def test_validate_config_fails_without_url(self):
        class BadAdapter(OpenAICompatibleAdapter):
            provider_name = "bad"
            default_model = "m"
            env_var = "X"
            base_url = ""
        adapter = BadAdapter()
        assert adapter.validate_config() is False
    
    def test_supports_streaming(self, adapter):
        assert adapter.supports_feature("streaming") is True
    
    def test_token_count_estimate(self, adapter):
        msgs = [{"role": "user", "content": "Hello world"}]
        tokens = adapter.token_count(msgs)
        assert tokens > 0
    
    def test_initialization(self, adapter):
        assert adapter.initialize() is True
        assert adapter.initialized is True