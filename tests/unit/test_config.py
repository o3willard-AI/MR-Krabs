#!/usr/bin/env python3
"""Unit tests for config.py - TOML configuration handling."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.config import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_CONFIG,
    _deep_copy,
    _deep_merge,
    _find_config,
    config_to_budget,
    load_config,
    _validate_config_version,
)
from src.core.cost import Decimal, FailureMode


class TestDeepCopy:
    """Tests for _deep_copy function."""
    
    def test_deep_copy_nested_dict(self):
        original = {"a": {"b": {"c": 1}}, "d": [1, 2, 3]}
        copied = _deep_copy(original)
        
        assert copied == original
        assert copied is not original
        assert copied["a"] is not original["a"]
        
        copied["a"]["b"]["c"] = 999
        assert original["a"]["b"]["c"] == 1


class TestDeepMerge:
    """Tests for _deep_merge function."""
    
    def test_deep_merge_simple(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        
        assert result == {"a": 1, "b": 3, "c": 4}
    
    def test_deep_merge_nested(self):
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}}
        result = _deep_merge(base, override)
        
        assert result == {"a": {"b": 10, "c": 2}, "d": 3}


class TestFindConfig:
    """Tests for _find_config function."""
    
    def test_returns_none_when_not_found(self, tmp_path):
        (tmp_path / "cwd").mkdir()
        (tmp_path / "home").mkdir()
        
        with patch('pathlib.Path.cwd', return_value=tmp_path / "cwd"), \
             patch('pathlib.Path.home', return_value=tmp_path / "home"):
            result = _find_config()
        
        assert result is None


class TestValidateConfigVersion:
    """Tests for _validate_config_version function."""
    
    def test_valid_version(self):
        user_config = {"version": CURRENT_CONFIG_VERSION}
        _validate_config_version(user_config)
    
    def test_invalid_version_raises(self):
        user_config = {"version": "2.0"}
        
        with pytest.raises(ValueError, match="Config version mismatch"):
            _validate_config_version(user_config)


class TestConfigToBudget:
    """Tests for config_to_budget function."""
    
    def test_defaults(self):
        config = {}
        budget = config_to_budget(config)
        
        assert budget.daily_limit_usd == Decimal("10.00")
        assert budget.task_limit_usd == Decimal("1.00")
        assert budget.warning_threshold == Decimal("0.8")
        assert budget.failure_mode == FailureMode.FAIL_OPEN_WITH_ALERT
    
    def test_custom_values(self):
        config = {
            "budget": {
                "daily_limit_usd": "25.00",
                "task_limit_usd": "2.00",
                "warning_threshold": "0.75",
                "failure_mode": "fail_closed",
            }
        }
        budget = config_to_budget(config)
        
        assert budget.daily_limit_usd == Decimal("25.00")
        assert budget.failure_mode == FailureMode.FAIL_CLOSED


class TestLoadConfig:
    """Tests for load_config function."""
    
    def test_returns_defaults_when_no_config(self, tmp_path):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        
        with patch('pathlib.Path.cwd', return_value=cwd), \
             patch('src.core.config._find_config', return_value=None):
            config = load_config()
        
        assert config == DEFAULT_CONFIG
        assert config["version"] == CURRENT_CONFIG_VERSION
    
    def test_merges_user_config(self, tmp_path):
        config_file = tmp_path / "cost_orchestrator.toml"
        config_file.write_text("""
version = "1.0"
[budget]
daily_limit_usd = "25.00"
""")
        
        with patch('pathlib.Path.cwd', return_value=tmp_path):
            config = load_config()
        
        assert config["budget"]["daily_limit_usd"] == "25.00"
        assert config["budget"]["task_limit_usd"] == "1.00"


class TestDefaultConfig:
    """Tests for DEFAULT_CONFIG constant."""
    
    def test_has_version(self):
        assert "version" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["version"] == CURRENT_CONFIG_VERSION
    
    def test_has_budget(self):
        assert "budget" in DEFAULT_CONFIG
        assert "daily_limit_usd" in DEFAULT_CONFIG["budget"]
    
    def test_has_tiers(self):
        assert "tiers" in DEFAULT_CONFIG
        assert "L0" in DEFAULT_CONFIG["tiers"]
        assert "L1" in DEFAULT_CONFIG["tiers"]
