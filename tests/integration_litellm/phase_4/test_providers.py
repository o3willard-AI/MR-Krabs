"""Phase 4: Provider adapter tests (unit tests, no API keys needed)."""
import pytest
from src.adapters.providers.deepseek import DeepSeekAdapter
from src.adapters.providers.groq import GroqAdapter
from src.adapters.providers.anthropic import AnthropicAdapter
from src.adapters.providers.mistral import MistralAdapter
from src.adapters.providers.vertex import VertexAdapter


class TestDeepSeekAdapter:
    def test_provider_metadata(self):
        a = DeepSeekAdapter()
        assert a.provider_name == "deepseek"
        assert a.default_model == "deepseek-chat"
        assert a.env_var == "DEEPSEEK_API_KEY"

    def test_list_models(self):
        a = DeepSeekAdapter()
        models = a.list_models()
        assert len(models) >= 2
        assert models[0].name in ("deepseek-chat", "deepseek-reasoner")

    def test_initialize(self):
        a = DeepSeekAdapter()
        assert a.initialize() is True


class TestGroqAdapter:
    def test_provider_metadata(self):
        a = GroqAdapter()
        assert a.provider_name == "groq"
        assert a.env_var == "GROQ_API_KEY"

    def test_list_models(self):
        a = GroqAdapter()
        models = a.list_models()
        assert len(models) >= 2


class TestAnthropicAdapter:
    def test_provider_metadata(self):
        a = AnthropicAdapter()
        assert a.provider_name == "anthropic"
        assert "claude" in a.default_model

    def test_list_models(self):
        a = AnthropicAdapter()
        models = a.list_models()
        assert len(models) >= 2
        assert all("claude" in m.name for m in models)

    def test_supports_features(self):
        a = AnthropicAdapter()
        assert a.supports_feature("streaming") is True
        assert a.supports_feature("vision") is True

    def test_validate_config_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        a = AnthropicAdapter()
        assert a.validate_config() is False


class TestMistralAdapter:
    def test_provider_metadata(self):
        a = MistralAdapter()
        assert a.provider_name == "mistral"

    def test_list_models(self):
        a = MistralAdapter()
        models = a.list_models()
        assert len(models) >= 2


class TestVertexAdapter:
    def test_provider_metadata(self):
        a = VertexAdapter()
        assert a.provider_name == "vertex"
        assert "gemini" in a.default_model

    def test_list_models(self):
        a = VertexAdapter()
        models = a.list_models()
        assert len(models) >= 2
        assert all("gemini" in m.name for m in models)

    def test_stream_not_implemented(self):
        import asyncio
        a = VertexAdapter()
        
        # Test that calling stream raises NotImplementedError
        async def test():
            await a.stream([{"role": "user", "content": "hi"}])
            
        with pytest.raises(NotImplementedError):
            asyncio.run(test())