#!/usr/bin/env python3
"""Model capability registry.

Tracks what each model can do: context window size, tool calling support,
supported languages, and other capabilities. Used for pre-flight checks
before routing tasks to models.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCapability:
    """Capabilities of a specific model."""

    model_id: str
    context_window: int = 8192
    max_output_tokens: int = 4096
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_streaming: bool = True
    known_languages: set[str] = field(
        default_factory=lambda: {"python", "javascript", "typescript"}
    )
    provider: str = ""
    is_free_tier: bool = False

    def can_handle_context(self, token_count: int) -> bool:
        return token_count <= self.context_window

    def can_handle_task(self, requires_tools: bool = False, requires_vision: bool = False) -> bool:
        if requires_tools and not self.supports_tool_calling:
            return False
        if requires_vision and not self.supports_vision:
            return False
        return True


MODEL_REGISTRY: dict[str, ModelCapability] = {
    "qwen/qwen3.5-397b-a17b": ModelCapability(
        model_id="qwen/qwen3.5-397b-a17b",
        context_window=131072,
        max_output_tokens=8192,
        supports_tool_calling=True,
        supports_streaming=True,
        known_languages={"python", "javascript", "typescript", "java", "go", "rust", "cpp"},
        provider="openrouter",
        is_free_tier=True,
    ),
    "qwen/qwen3-coder-30b": ModelCapability(
        model_id="qwen/qwen3-coder-30b",
        context_window=32768,
        max_output_tokens=8192,
        supports_tool_calling=True,
        supports_streaming=True,
        known_languages={"python", "javascript", "typescript", "java", "go"},
        provider="lmstudio",
        is_free_tier=True,
    ),
    "x-ai/grok-4.1-fast": ModelCapability(
        model_id="x-ai/grok-4.1-fast",
        context_window=131072,
        max_output_tokens=8192,
        supports_tool_calling=True,
        supports_streaming=True,
        known_languages={
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "cpp",
            "csharp",
        },
        provider="openrouter",
    ),
    "minimax/minimax-m2.7": ModelCapability(
        model_id="minimax/minimax-m2.7",
        context_window=131072,
        max_output_tokens=8192,
        supports_tool_calling=False,
        supports_streaming=True,
        known_languages={"python", "javascript", "typescript"},
        provider="openrouter",
    ),
    "anthropic/claude-sonnet-4.6": ModelCapability(
        model_id="anthropic/claude-sonnet-4.6",
        context_window=200000,
        max_output_tokens=8192,
        supports_tool_calling=True,
        supports_streaming=True,
        known_languages={
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "cpp",
            "csharp",
            "ruby",
            "php",
        },
        provider="openrouter",
    ),
    "anthropic/claude-opus-4.6": ModelCapability(
        model_id="anthropic/claude-opus-4.6",
        context_window=200000,
        max_output_tokens=8192,
        supports_tool_calling=True,
        supports_streaming=True,
        known_languages={
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "cpp",
            "csharp",
            "ruby",
            "php",
            "swift",
            "kotlin",
        },
        provider="openrouter",
    ),
}


def get_capable_models(token_count: int = 0, requires_tools: bool = False, requires_vision: bool = False) -> list[str]:
    """Return model IDs that can handle the given requirements, sorted by capability (most capable first)."""
    capable = []
    for model_id, cap in MODEL_REGISTRY.items():
        if token_count > 0 and not cap.can_handle_context(token_count):
            continue
        if not cap.can_handle_task(requires_tools=requires_tools, requires_vision=requires_vision):
            continue
        capable.append((model_id, cap))

    # Sort by capability: free tier first, then by context window size (largest first)
    capable.sort(key=lambda x: (0 if x[1].is_free_tier else 1, -x[1].context_window))
    return [m[0] for m in capable]


class CapabilityChecker:
    """Checks if a model can handle a given task's requirements."""

    def __init__(self, registry: dict[str, ModelCapability] | None = None):
        self._registry = registry or MODEL_REGISTRY

    def check(
        self,
        model_id: str,
        token_count: int = 0,
        requires_tools: bool = False,
        requires_vision: bool = False,
    ) -> list[str]:
        """Check if a model can handle the task. Returns list of issues (empty = OK)."""
        capability = self._registry.get(model_id)
        if capability is None:
            return [f"Unknown model: {model_id} (no capability data available)"]

        issues = []
        if token_count > 0 and not capability.can_handle_context(token_count):
            issues.append(
                f"Context too large: {token_count} tokens > {capability.context_window} window"
            )
        if not capability.can_handle_task(
            requires_tools=requires_tools, requires_vision=requires_vision
        ):
            if requires_tools and not capability.supports_tool_calling:
                issues.append(f"Model {model_id} does not support tool calling")
            if requires_vision and not capability.supports_vision:
                issues.append(f"Model {model_id} does not support vision")
        return issues

    def find_capable_models(
        self,
        token_count: int = 0,
        requires_tools: bool = False,
        requires_vision: bool = False,
        prefer_free: bool = False,
    ) -> list[str]:
        """Find all models that can handle the task, sorted by capability."""
        capable = []
        for model_id, cap in self._registry.items():
            issues = self.check(model_id, token_count, requires_tools, requires_vision)
            if not issues:
                capable.append((model_id, cap))

        capable.sort(key=lambda x: (x[1].is_free_tier if prefer_free else 0, -x[1].context_window))
        return [m[0] for m in capable]

    def register(self, capability: ModelCapability) -> None:
        """Register or update a model's capabilities."""
        self._registry[capability.model_id] = capability
