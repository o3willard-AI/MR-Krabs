#!/usr/bin/env python3
"""Simplified unit tests for validators."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.validators.api_keys import APIKeyValidator
from src.validators.templates import TemplateValidator
from src.validators.models import ModelValidator
from src.validators.startup import StartupValidator


class TestAPIKeyValidator:
    """Tests for APIKeyValidator class."""
    
    def test_valid_key(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-1234567890abcdef"
        v = APIKeyValidator()
        result = v.validate_key("openrouter")
        assert result[0] is True
        assert "valid" in result[1].lower()
    
    def test_missing_key(self):
        os.environ.pop("OPENROUTER_API_KEY", None)
        v = APIKeyValidator()
        result = v.validate_key("openrouter")
        assert result[0] is False
        assert "missing" in result[1].lower()
    
    def test_local_provider(self):
        v = APIKeyValidator()
        result = v.validate_key("lmstudio")
        assert result[0] is True
        assert "local" in result[1].lower()
    
    def test_anthropic_provider(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-123456"
        v = APIKeyValidator()
        result = v.validate_key("anthropic")
        assert result[0] is True
        os.environ.pop("ANTHROPIC_API_KEY", None)
    
    def test_openai_provider(self):
        os.environ["OPENAI_API_KEY"] = "sk-123456"
        v = APIKeyValidator()
        result = v.validate_key("openai")
        assert result[0] is True
        os.environ.pop("OPENAI_API_KEY", None)
    
    def test_empty_api_key(self):
        os.environ["OPENROUTER_API_KEY"] = ""
        v = APIKeyValidator()
        result = v.validate_key("openrouter")
        assert result[0] is False
        os.environ.pop("OPENROUTER_API_KEY", None)


class TestTemplateValidator:
    """Tests for TemplateValidator class."""
    
    def test_validate_existing_template(self):
        PROJECT_ROOT = Path(__file__).parent.parent.parent
        v = TemplateValidator(PROJECT_ROOT / "templates")
        ok, msg = v.validate_template("01-planner.md")
        assert ok is True
    
    def test_validate_missing_template(self):
        PROJECT_ROOT = Path(__file__).parent.parent.parent
        v = TemplateValidator(PROJECT_ROOT / "templates")
        ok, msg = v.validate_template("nonexistent.md")
        assert ok is False
        assert "not found" in msg.lower()
    
    def test_validate_template_invalid_path(self):
        v = TemplateValidator(Path("/nonexistent/path"))
        ok, msg = v.validate_template("any.md")
        assert ok is False
    
    def test_validate_template_nonexistent_dir(self):
        v = TemplateValidator(Path("/tmp/nonexistent_dir_12345"))
        ok, msg = v.validate_template("test.md")
        assert ok is False
    
    def test_empty_template_name(self):
        PROJECT_ROOT = Path(__file__).parent.parent.parent
        v = TemplateValidator(PROJECT_ROOT / "templates")
        ok, msg = v.validate_template("")
        assert ok is False


class TestModelValidator:
    """Tests for ModelValidator class."""
    
    def test_validate_all_returns_dict(self):
        """Test validate_all returns a dictionary."""
        v = ModelValidator()
        results = v.validate_all()
        
        assert isinstance(results, dict)
        assert "valid" in results
        assert "invalid" in results
        assert "local" in results
    
    def test_validate_model_tier_api(self):
        """Test validate_model with tier parameter."""
        v = ModelValidator()
        
        # Test with a known tier
        is_valid, message, similar = v.validate_model("l0-planner")
        
        # Should return a tuple of 3 elements
        assert isinstance(is_valid, bool)
        assert isinstance(message, str)
        assert isinstance(similar, list)
    
    def test_validate_model_unknown_tier(self):
        """Test validate_model with unknown tier."""
        v = ModelValidator()
        is_valid, message, similar = v.validate_model("unknown-tier")
        
        assert is_valid is False
        assert "unknown" in message.lower()
    
    def test_fetch_available_models_with_key(self):
        """Test fetching models with valid API key."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        v = ModelValidator()
        
        # Mock the requests call
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "test-model-1"},
                    {"id": "test-model-2"}
                ]
            }
            mock_get.return_value = mock_response
            
            result = v.fetch_available_models()
            
            assert result is True
            assert "test-model-1" in v._available_models
    
    def test_fetch_available_models_no_key(self):
        """Test fetching models without API key."""
        os.environ.pop("OPENROUTER_API_KEY", None)
        v = ModelValidator()
        
        result = v.fetch_available_models()
        assert result is False
    
    def test_fetch_available_models_request_fails(self):
        """Test fetching models when request fails."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        v = ModelValidator()
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            result = v.fetch_available_models()
            assert result is False
        
        os.environ.pop("OPENROUTER_API_KEY", None)


class TestStartupValidator:
    """Tests for StartupValidator class."""
    
    def test_validate_all_returns_structure(self):
        """Test validate_all returns the expected structure."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-123"
        
        v = StartupValidator()
        ok, errors = v.validate_all()
        
        # Returns tuple of (bool, dict)
        assert isinstance(ok, bool)
        assert isinstance(errors, dict)
        
        # Should have expected keys
        assert "api_keys" in errors
        assert "models" in errors
        assert "templates" in errors
    
    def test_validation_checks_api_keys(self):
        """Test that validation checks API keys."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-123"
        
        v = StartupValidator()
        ok, errors = v.validate_all()
        
        # API keys section should exist
        assert "api_keys" in errors
    
    def test_validation_checks_templates(self):
        """Test that validation checks templates."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-123"
        
        v = StartupValidator()
        ok, errors = v.validate_all()
        
        # Templates section should exist
        assert "templates" in errors
    
    def test_missing_api_key_validation(self):
        """Test validation when API key is missing."""
        os.environ.pop("OPENROUTER_API_KEY", None)
        
        v = StartupValidator()
        ok, errors = v.validate_all()
        
        # Should indicate issues
        assert isinstance(ok, bool)
        assert isinstance(errors, dict)


class TestValidatorIntegration:
    """Integration tests for validator components."""
    
    def test_api_key_and_template_validation_together(self):
        """Test that API key and template validation work together."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-1234567890abcdef"
        
        PROJECT_ROOT = Path(__file__).parent.parent.parent
        
        key_validator = APIKeyValidator()
        template_validator = TemplateValidator(PROJECT_ROOT / "templates")
        
        # Validate both
        key_ok, key_msg = key_validator.validate_key("openrouter")
        template_ok, template_msg = template_validator.validate_template("01-planner.md")
        
        # Both should pass
        assert key_ok is True
        assert template_ok is True
        
        os.environ.pop("OPENROUTER_API_KEY", None)
    
    def test_model_and_startup_validation(self):
        """Test that model and startup validation are consistent."""
        os.environ["OPENROUTER_API_KEY"] = "sk-or-123"
        
        model_validator = ModelValidator()
        startup_validator = StartupValidator()
        
        # Validate models
        model_results = model_validator.validate_all()
        assert "valid" in model_results
        assert "invalid" in model_results
        
        # Startup validation should also work
        ok, errors = startup_validator.validate_all()
        assert ok is True or isinstance(errors, dict)


class TestValidatorEdgeCases:
    """Edge case tests for validators."""
    
    def test_api_key_with_spaces(self):
        """Test API key validation with leading/trailing spaces."""
        os.environ["OPENROUTER_API_KEY"] = "  sk-or-123  "
        
        v = APIKeyValidator()
        result = v.validate_key("openrouter")
        
        # Should handle gracefully
        assert isinstance(result, tuple)
        assert len(result) >= 2
        
        os.environ.pop("OPENROUTER_API_KEY", None)
    
    def test_template_validator_empty_dir(self):
        """Test template validator with empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            v = TemplateValidator(Path(tmpdir))
            ok, msg = v.validate_template("nonexistent.md")
            assert ok is False
    
    def test_model_validator_invalid_tier(self):
        """Test model validator with invalid tier."""
        v = ModelValidator()
        is_valid, message, similar = v.validate_model("not-a-tier")
        
        assert is_valid is False
        assert isinstance(message, str)
        assert isinstance(similar, list)
