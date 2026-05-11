#!/usr/bin/env python3
"""Unit tests for model capability registry and pre-flight checks."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.model_capabilities import (
    ModelCapability, MODEL_REGISTRY, get_capable_models, CapabilityChecker,
)


class TestModelCapability:
    """Test individual ModelCapability methods."""

    def test_context_window_exceeded_rejected(self):
        """Model with 8K window rejects 20K tokens."""
        cap = ModelCapability(
            model_id="test-small",
            context_window=8192,
            supports_tool_calling=True,
        )
        assert cap.can_handle_context(5000) is True
        assert cap.can_handle_context(8192) is True
        assert cap.can_handle_context(20000) is False

    def test_tool_calling_required_but_unsupported(self):
        """Model without tool support fails tool-required check."""
        cap_no_tools = ModelCapability(
            model_id="test-no-tools",
            context_window=32768,
            supports_tool_calling=False,
        )
        assert cap_no_tools.can_handle_task(requires_tools=False) is True
        assert cap_no_tools.can_handle_task(requires_tools=True) is False

    def test_vision_required_but_unsupported(self):
        """Model without vision support fails vision-required check."""
        cap_no_vision = ModelCapability(
            model_id="test-no-vision",
            context_window=32768,
            supports_vision=False,
        )
        assert cap_no_vision.can_handle_task(requires_vision=False) is True
        assert cap_no_vision.can_handle_task(requires_vision=True) is False

    def test_capable_model_passes_all_checks(self):
        """Fully capable model passes all checks."""
        cap = ModelCapability(
            model_id="test-capable",
            context_window=131072,
            supports_tool_calling=True,
            supports_vision=True,
        )
        assert cap.can_handle_context(100000) is True
        assert cap.can_handle_task(requires_tools=True, requires_vision=True) is True


class TestGetCapableModels:
    """Test get_capable_models helper function."""

    def test_filters_by_context_window(self):
        """Only models with sufficient context window are returned."""
        models = get_capable_models(token_count=50000)
        for model_id in models:
            cap = MODEL_REGISTRY[model_id]
            assert cap.context_window >= 50000, (
                f"{model_id} returned but has context_window={cap.context_window}"
            )

    def test_filters_by_tool_calling(self):
        """Only models with tool support are returned when requires_tools=True."""
        models = get_capable_models(requires_tools=True)
        for model_id in models:
            cap = MODEL_REGISTRY[model_id]
            assert cap.supports_tool_calling is True, (
                f"{model_id} returned but lacks tool calling"
            )

    def test_returns_sorted_by_capability(self):
        """Results are sorted: free tier first, then by context window descending."""
        models = get_capable_models()
        assert len(models) > 0
        free_models = [m for m in models if MODEL_REGISTRY[m].is_free_tier]
        paid_models = [m for m in models if not MODEL_REGISTRY[m].is_free_tier]
        # All free models should come before paid models
        if free_models and paid_models:
            first_paid_idx = models.index(paid_models[0])
            last_free_idx = max(models.index(fm) for fm in free_models)
            assert last_free_idx < first_paid_idx, "Free models should sort before paid models"

    def test_empty_when_no_model_capable(self):
        """Returns empty list when no model meets requirements."""
        models = get_capable_models(token_count=999_999_999)
        assert models == []


class TestCapabilityChecker:
    """Test CapabilityChecker class."""

    def test_unknown_model_assumed_capable(self):
        """Model not in registry should not crash — passes through."""
        checker = CapabilityChecker()
        # Unknown model should return a warning but not crash
        issues = checker.check("unknown-model-123", token_count=5000)
        assert "Unknown model" in issues[0]


class TestModelRegistry:
    """Test registry completeness."""

    def test_all_registry_models_valid(self):
        """All models in registry have required fields."""
        for model_id, cap in MODEL_REGISTRY.items():
            assert cap.model_id == model_id
            assert cap.context_window > 0, f"{model_id}: context_window must be > 0"
            assert cap.provider != "", f"{model_id}: provider must not be empty"

    def test_registry_covers_common_models(self):
        """Registry includes models from the default tier configuration."""
        expected_models = [
            "qwen/qwen3.5-397b-a17b",
            "qwen/qwen3-coder-30b",
            "x-ai/grok-4.1-fast",
            "anthropic/claude-sonnet-4.6",
        ]
        for model in expected_models:
            assert model in MODEL_REGISTRY, f"{model} missing from MODEL_REGISTRY"
