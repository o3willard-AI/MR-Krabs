#!/usr/bin/env python3
"""Tests for prompt_format.py."""

import pytest
from src.core.prompt_format import (
    PromptFormat, FORMAT_REGISTRY, detect_format, format_messages
)

class TestEnum:
    def test_values(self):
        assert PromptFormat.OPENAI_CHAT.value == "openai_chat"
        assert PromptFormat.CHATML.value == "chatml"
        assert PromptFormat.LLAMA.value == "llama"

class TestRegistry:
    def test_openai(self):
        assert FORMAT_REGISTRY["openai/"] == PromptFormat.OPENAI_CHAT
    def test_mistral(self):
        assert FORMAT_REGISTRY["mistral/"] == PromptFormat.CHATML
    def test_llama(self):
        assert FORMAT_REGISTRY["meta-llama/"] == PromptFormat.LLAMA

class TestDetectFormat:
    def test_openai_model(self):
        assert detect_format("openai/gpt-4") == PromptFormat.OPENAI_CHAT
    def test_anthropic_model(self):
        assert detect_format("anthropic/claude") == PromptFormat.OPENAI_CHAT
    def test_google_model(self):
        assert detect_format("google/gemma") == PromptFormat.OPENAI_CHAT
    def test_llama_model(self):
        assert detect_format("meta-llama/Llama-3") == PromptFormat.LLAMA
    def test_mistral_model(self):
        assert detect_format("mistralai/Mistral") == PromptFormat.CHATML
    def test_unknown_defaults(self):
        assert detect_format("unknown/model") == PromptFormat.OPENAI_CHAT
    def test_case_insensitive(self):
        assert detect_format("META-llama/Llama") == PromptFormat.LLAMA

class TestFormatMessages:
    def test_openai_format(self):
        import json
        msgs = [{"role": "user", "content": "hello"}]
        result = format_messages(msgs, PromptFormat.OPENAI_CHAT)
        parsed = json.loads(result)
        assert parsed == msgs
    def test_chatml_format(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = format_messages(msgs, PromptFormat.CHATML)
        assert "<|im_start|>user" in result
        assert "hello" in result
        assert "<|im_end|>" in result
    def test_llama_format(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = format_messages(msgs, PromptFormat.LLAMA, "system prompt")
        assert "<|start_header_id|>system" in result
        assert "<|start_header_id|>user" in result
        assert "hello" in result
    def test_alpaca_format(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = format_messages(msgs, PromptFormat.ALPACA, "sys")
        assert "### System:" in result
        assert "### Instruction:" in result
        assert "hello" in result
    def test_raw_format(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = format_messages(msgs, PromptFormat.RAW)
        assert "[user] hello" in result


class TestAlpacaFormatDetailed:
    """Additional alpaca format tests."""
    def test_alpaca_with_system_role(self):
        """Test alpaca format skips system roles in message list."""
        msgs = [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hello"}
        ]
        result = format_messages(msgs, PromptFormat.ALPACA)
        # Should not process system role in message loop
        assert "### Instruction:" in result
    
    def test_alpaca_with_assistant_role(self):
        """Test alpaca format handles assistant roles."""
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"}
        ]
        result = format_messages(msgs, PromptFormat.ALPACA)
        assert "### Response:" in result
