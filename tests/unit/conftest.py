#!/usr/bin/env python3
"""Shared test fixtures for MR-Krabs unit tests.

Provides a temporary config.yaml via MRKRABS_CONFIG env var.
Resets the config cache between each test to prevent cross-pollution.
"""

import os

import pytest

from src.core.config_loader import reset_config_cache


TEST_CONFIG = """\
version: "1.0"

providers:
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    timeout: 300
  lmstudio:
    type: openai_compatible
    base_url: http://192.168.101.17:1234/v1
    timeout: 1800

models:
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]
  l0-planner:
    provider: openrouter
    model: google/gemini-2.5-pro
    temperature: 0.0
    max_tokens: 32768
    roles: [planner]
    tools: [file_read, file_write]
  l0-reviewer:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.3
    max_tokens: 4096
    roles: [reviewer]
  l0-coder:
    provider: lmstudio
    model: qwen3-coder-30b-a3b-instruct
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]
    tools: [file_write, file_read]
  l1-coder:
    provider: openrouter
    model: google/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]
  l2-coder:
    provider: openrouter
    model: anthropic/claude-haiku-4.5
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]
  l3-coder:
    provider: openrouter
    model: anthropic/claude-sonnet-4.6
    temperature: 0.0
    max_tokens: 8192
    roles: [coder]
    tools: [file_write, file_read]
  l3-architect:
    provider: openrouter
    model: anthropic/claude-opus-4.6
    temperature: 0.3
    max_tokens: 4096
    roles: [architect]
  l0-sushi:
    provider: lmstudio
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [coder]
    tools: [file_write, file_read]
    profile: sushi-9b
  l0-sushi-planner:
    provider: lmstudio
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 4096
    roles: [planner]
    profile: sushi-9b
  l0-sushi-judge:
    provider: lmstudio
    model: qwen3.5-9b-sushi-coder-rl
    temperature: 0.0
    max_tokens: 2048
    roles: [judge]
    profile: sushi-9b
  l0-gptoss:
    provider: lmstudio
    model: gpt-oss-20b-claude-opus-sonnet-reasoning-i1
    temperature: 0.0
    max_tokens: 8192
    roles: [planner]
    profile: gpt-oss-20b
  principal:
    provider: ""
    model: ""
    roles: [principal]

workflows:
  code:
    tiers: [l0-coder, l0-sushi, l1-coder, l2-coder, l3-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
  plan:
    tiers: [l0-planner, l0-sushi-planner, l0-gptoss, principal]
    max_retries_per_tier: 3
    judge_model: judge
  review:
    tiers: [l0-reviewer, principal]
    max_retries_per_tier: 2
    judge_model: judge

tier_failure_actions:
  l0-coder: log_only
  l1-coder: notify_and_escalate
  l2-coder: notify_and_wait
  l3-coder: notify_and_wait
"""


@pytest.fixture(scope="session")
def test_config_file(tmp_path_factory):
    """Create a session-scoped test config.yaml and set MRKRABS_CONFIG env."""
    config_file = tmp_path_factory.mktemp("mrkrabs_test") / "config.yaml"
    config_file.write_text(TEST_CONFIG)
    return str(config_file)


@pytest.fixture(autouse=True)
def _setup_test_config(test_config_file, monkeypatch):
    """Set MRKRABS_CONFIG env var and reset cache for each test."""
    monkeypatch.setenv("MRKRABS_CONFIG", test_config_file)
    reset_config_cache()
