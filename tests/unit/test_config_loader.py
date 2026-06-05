#!/usr/bin/env python3
"""Unit tests for config_loader.py — Phase D: YAML-driven, no legacy auto-gen."""

import tempfile
from pathlib import Path

import pytest

from src.core.config_loader import (
    BudgetConfig,
    ConfigNotFoundError,
    ModelConfig,
    MrKrabsConfig,
    ProfileConfig,
    ProviderConfig,
    WorkflowConfig,
    _build_role_hierarchy,
    _extract_tier_number,
    _infer_role,
    _legacy_key,
    _normalize_model_key,
    _tier_sort_key,
    legacy_models,
    load_config,
    reset_config_cache,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _write_config_yaml(content: str, tmp_path: Path) -> Path:
    """Write a YAML config file to a temp directory and return its path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(content)
    return config_file


MINIMAL_CONFIG = """\
version: "1.0"

providers:
  litellm:
    type: openai_compatible
    base_url: http://192.168.101.42:4000/v1
    api_key_env: LITELLM_MASTER_KEY
    timeout: 1800
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

models:
  judge:
    provider: openrouter
    model: deepseek/deepseek-r1
    temperature: 0.1
    max_tokens: 1024
    roles: [judge]
  l0-planner:
    provider: litellm
    model: mrk-planner-l0
    temperature: 0.0
    max_tokens: 16384
    roles: [planner]
  l0-coder:
    provider: litellm
    model: mrk-coder-l0
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
  principal:
    provider: ""
    model: ""
    roles: [principal]

workflows:
  code:
    tiers: [l0-coder, l1-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge
  plan:
    tiers: [l0-planner, principal]
    max_retries_per_tier: 3
    judge_model: judge

tier_failure_actions:
  l0-coder: log_only
  l1-coder: notify_and_escalate
"""


# ═══════════════════════════════════════════════════════════════════════
# Config Not Found
# ═══════════════════════════════════════════════════════════════════════


class TestConfigNotFound:
    """Tests for ConfigNotFoundError when no config exists."""

    def test_no_config_raises(self, tmp_path):
        """load_config raises ConfigNotFoundError when no config.yaml and no legacy."""
        # Point to a nonexistent path — no legacy auto-gen anymore
        with pytest.raises(ConfigNotFoundError):
            load_config(path=str(tmp_path / "nonexistent" / "config.yaml"))


# ═══════════════════════════════════════════════════════════════════════
# YAML File Loading
# ═══════════════════════════════════════════════════════════════════════


class TestYamlFileLoading:
    """Tests for loading MrKrabsConfig from YAML files."""

    def test_loads_valid_config(self, tmp_path):
        config_file = _write_config_yaml(MINIMAL_CONFIG, tmp_path)
        config = load_config(path=str(config_file))

        assert isinstance(config, MrKrabsConfig)
        assert len(config.providers) == 2
        assert len(config.models) == 5
        assert len(config.workflows) == 2

    def test_model_provider_reference(self, tmp_path):
        config_file = _write_config_yaml(MINIMAL_CONFIG, tmp_path)
        config = load_config(path=str(config_file))

        coder = config.models["l0-coder"]
        assert coder.provider == "litellm"
        provider = config.providers["litellm"]
        assert "192.168.101.42" in provider.base_url

    def test_workflow_tiers_resolve(self, tmp_path):
        config_file = _write_config_yaml(MINIMAL_CONFIG, tmp_path)
        config = load_config(path=str(config_file))

        wf = config.workflows["code"]
        assert wf.tiers == ["l0-coder", "l1-coder", "principal"]

    def test_defaults_applied(self, tmp_path):
        minimal = """\
version: "1.0"
providers:
  test:
    base_url: http://localhost:8080/v1
models:
  test-model:
    provider: test
    model: test-model-1
    roles: [coder]
"""
        config_file = _write_config_yaml(minimal, tmp_path)
        config = load_config(path=str(config_file))

        model = config.models["test-model"]
        assert model.temperature == 0.7
        assert model.max_tokens == 4096
        assert model.tools == []

        provider = config.providers["test"]
        assert provider.timeout == 300

    def test_missing_provider_raises(self, tmp_path):
        bad_config = """\
version: "1.0"
models:
  orphan:
    provider: nonexistent
    model: some-model
    roles: [coder]
"""
        config_file = _write_config_yaml(bad_config, tmp_path)
        with pytest.raises(ValueError, match="provider"):
            load_config(path=str(config_file))

    def test_missing_workflow_tier_raises(self, tmp_path):
        bad_config = """\
version: "1.0"
providers:
  openrouter:
    base_url: https://openrouter.ai/api/v1
models:
  only-model:
    provider: openrouter
    model: test
    roles: [coder]
workflows:
  code:
    tiers: [nonexistent-tier]
"""
        config_file = _write_config_yaml(bad_config, tmp_path)
        with pytest.raises(ValueError, match="tier"):
            load_config(path=str(config_file))

    def test_profiles_parsed(self, tmp_path):
        config_with_profile = MINIMAL_CONFIG + """\
profiles:
  test-profile:
    prepend: "You are a test model."
    known_failures:
      - trigger: "bad_pattern"
        feedback: "Fix the bad pattern"
        severity: error
"""
        config_file = _write_config_yaml(config_with_profile, tmp_path)
        config = load_config(path=str(config_file))

        profile = config.profiles.get("test-profile")
        assert profile is not None
        assert profile.prepend == "You are a test model."
        assert len(profile.known_failures) == 1
        assert profile.known_failures[0].trigger == "bad_pattern"

    def test_budget_parsed(self, tmp_path):
        config_with_budget = MINIMAL_CONFIG + """\
budget:
  daily_limit_usd: 25.00
  budget_awareness: true
  tier_thresholds:
    0.8: l2-coder
    0.5: l1-coder
"""
        config_file = _write_config_yaml(config_with_budget, tmp_path)
        config = load_config(path=str(config_file))

        assert config.budget.daily_limit_usd == 25.00
        assert config.budget.budget_awareness is True
        assert config.budget.tier_thresholds == {"0.8": "l2-coder", "0.5": "l1-coder"}


# ═══════════════════════════════════════════════════════════════════════
# Legacy Models Wrapper (uses our config.yaml, not auto-gen)
# ═══════════════════════════════════════════════════════════════════════


class TestLegacyModelsWrapper:
    """Tests for legacy_models() — MrKrabsConfig → old MODELS dict format."""

    @pytest.fixture
    def config(self, tmp_path):
        config_file = _write_config_yaml(MINIMAL_CONFIG, tmp_path)
        reset_config_cache()
        return load_config(path=str(config_file))

    def test_returns_old_format_dict(self, config):
        result = legacy_models(config)
        assert isinstance(result, dict)
        assert "Judge" in result

        judge = result["Judge"]
        assert "provider" in judge
        assert "model" in judge
        assert "base_url" in judge
        assert "temperature" in judge

    def test_includes_all_model_keys(self, config):
        result = legacy_models(config)
        # Legacy keys use uppercase format
        assert "L0-Coder" in result
        assert "L1-Coder" in result
        assert "L0-Planner" in result


# ═══════════════════════════════════════════════════════════════════════
# Config Lookup Helpers
# ═══════════════════════════════════════════════════════════════════════


class TestConfigLookupHelpers:
    @pytest.fixture
    def config(self, tmp_path):
        config_file = _write_config_yaml(MINIMAL_CONFIG, tmp_path)
        reset_config_cache()
        return load_config(path=str(config_file))

    def test_get_model_found(self, config):
        model = config.get_model("l0-coder")
        assert model is not None
        assert model.key == "l0-coder"

    def test_get_model_not_found(self, config):
        assert config.get_model("nonexistent") is None

    def test_get_provider_found(self, config):
        provider = config.get_provider("openrouter")
        assert provider is not None
        assert provider.name == "openrouter"

    def test_models_for_role(self, config):
        coders = config.models_for_role("coder")
        assert "l0-coder" in coders
        assert "l1-coder" in coders

        planners = config.models_for_role("planner")
        assert "l0-planner" in planners

    def test_available_roles(self, config):
        roles = config.available_roles
        assert "coder" in roles
        assert "planner" in roles
        assert "judge" in roles
        assert "principal" in roles


# ═══════════════════════════════════════════════════════════════════════
# Key Normalization
# ═══════════════════════════════════════════════════════════════════════


class TestNormalizeModelKey:
    def test_l0_coder(self):
        assert _normalize_model_key("L0-Coder") == "l0-coder"

    def test_judge(self):
        assert _normalize_model_key("Judge") == "judge"

    def test_principal(self):
        assert _normalize_model_key("Principal") == "principal"


class TestLegacyKey:
    def test_l0_coder(self):
        assert _legacy_key("l0-coder") == "L0-Coder"

    def test_l0_planner(self):
        assert _legacy_key("l0-planner") == "L0-Planner"

    def test_judge(self):
        assert _legacy_key("judge") == "Judge"

    def test_principal(self):
        assert _legacy_key("principal") == "Principal"


class TestInferRole:
    def test_explicit_role_wins(self):
        assert _infer_role({"role": "planner"}, "L0-Coder") == "planner"

    def test_infer_from_coder_key(self):
        assert _infer_role({}, "L1-Coder") == "coder"

    def test_fallback_to_coder(self):
        assert _infer_role({}, "Unknown-Model") == "coder"


class TestExtractTierNumber:
    def test_l0(self):
        assert _extract_tier_number("l0-coder") == 0

    def test_l2(self):
        assert _extract_tier_number("l2-planner") == 2

    def test_no_tier_defaults_zero(self):
        assert _extract_tier_number("judge") == 0

    def test_sort_order(self):
        keys = ["l2-coder", "l0-coder", "l1-coder", "l3-coder"]
        sorted_keys = sorted(keys, key=_tier_sort_key)
        assert sorted_keys == ["l0-coder", "l1-coder", "l2-coder", "l3-coder"]


class TestBuildRoleHierarchy:
    def test_groups_by_role(self):
        models = {
            "l0-coder": ModelConfig(key="l0-coder", provider="test", model="m1", roles=["coder"]),
            "l0-planner": ModelConfig(key="l0-planner", provider="test", model="m2", roles=["planner"]),
        }
        hierarchy = _build_role_hierarchy(models)
        assert hierarchy["coder"] == ["l0-coder"]
        assert hierarchy["planner"] == ["l0-planner"]
