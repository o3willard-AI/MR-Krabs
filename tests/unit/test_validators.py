#!/usr/bin/env python3
"""Unit tests for validators."""
import os, sys, pytest
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.validators.api_keys import APIKeyValidator
from src.validators.templates import TemplateValidator

class TestAPIKeyValidator:
    def test_valid_key(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test123456789"
        v = APIKeyValidator()
        r = v.validate_key("openrouter")
        assert r[0] is True
    
    def test_missing_key(self):
        os.environ.pop("OPENROUTER_API_KEY", None)
        v = APIKeyValidator()
        r = v.validate_key("openrouter")
        assert r[0] is False
        assert "Missing" in r[1]
    
    def test_local_provider(self):
        v = APIKeyValidator()
        r = v.validate_key("lmstudio")
        assert r[0] is True

class TestTemplateValidator:
    def test_validate_existing_template(self):
        v = TemplateValidator(PROJECT_ROOT / "templates")
        ok, msg = v.validate_template("01-planner.md")
        assert ok is True
    
    def test_validate_missing_template(self):
        v = TemplateValidator(PROJECT_ROOT / "templates")
        ok, msg = v.validate_template("nonexistent.md")
        assert ok is False
        assert "not found" in msg.lower()
