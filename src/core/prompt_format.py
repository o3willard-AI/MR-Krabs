#!/usr/bin/env python3
"""Prompt format compatibility layer.

Handles automatic conversion between different prompt formats required
by different models (ChatML, Llama, OpenAI chat, etc.).
"""

from __future__ import annotations

from enum import Enum


class PromptFormat(Enum):
    OPENAI_CHAT = "openai_chat"
    CHATML = "chatml"
    LLAMA = "llama"
    ALPACA = "alpaca"
    RAW = "raw"


FORMAT_REGISTRY: dict[str, PromptFormat] = {
    "openai/": PromptFormat.OPENAI_CHAT,
    "anthropic/": PromptFormat.OPENAI_CHAT,
    "google/": PromptFormat.OPENAI_CHAT,
    "meta-llama/": PromptFormat.LLAMA,
    "llama-": PromptFormat.LLAMA,
    "mistral/": PromptFormat.CHATML,
    "microsoft/": PromptFormat.CHATML,
}


def detect_format(model_id: str) -> PromptFormat:
    """Detect the prompt format for a given model."""
    for prefix, fmt in FORMAT_REGISTRY.items():
        if model_id.startswith(prefix) or prefix.rstrip("/") in model_id.lower():
            return fmt
    return PromptFormat.OPENAI_CHAT


def format_messages(
    messages: list[dict[str, str]],
    target_format: PromptFormat,
    system_prompt: str | None = None,
) -> str:
    """Format messages for the target prompt format.

    Args:
        messages: List of {role, content} dicts.
        target_format: Target prompt format.
        system_prompt: Optional system prompt (used for formats that need it separate).

    Returns:
        Formatted prompt string.
    """
    if target_format == PromptFormat.OPENAI_CHAT:
        return _format_openai_chat(messages)
    elif target_format == PromptFormat.CHATML:
        return _format_chatml(messages)
    elif target_format == PromptFormat.LLAMA:
        return _format_llama(messages, system_prompt)
    elif target_format == PromptFormat.ALPACA:
        return _format_alpaca(messages, system_prompt)
    else:
        return _format_raw(messages)


def _format_openai_chat(messages: list[dict[str, str]]) -> str:
    """OpenAI chat format (JSON array of messages)."""
    import json

    return json.dumps(messages)


def _format_chatml(messages: list[dict[str, str]]) -> str:
    """ChatML format: <|im_start|>role\ncontent<|im_end|>"""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


def _format_llama(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """Llama 3 Instruct format: <|start_header_id|>role<|end_header_id|>\n\ncontent<|eot_id|>"""
    parts = []
    if system_prompt:
        parts.append(
            "<|start_header_id|>system<|end_header_id|>\n\n" + system_prompt + "<|eot_id|>"
        )
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            continue
        parts.append(f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>")
    parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "\n".join(parts)


def _format_alpaca(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """Alpaca format: ### Instruction/### Input/### Response"""
    parts = []
    if system_prompt:
        parts.append(f"### System:\n{system_prompt}\n")
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"### Instruction:\n{content}\n")
        elif role == "assistant":
            parts.append(f"### Response:\n{content}\n")
    parts.append("### Response:\n")
    return "\n".join(parts)


def _format_raw(messages: list[dict[str, str]]) -> str:
    """Raw format: concatenate all messages with role labels."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"[{role}] {content}")
    return "\n".join(parts)
