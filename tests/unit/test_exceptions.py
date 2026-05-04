#!/usr/bin/env python3
"""Unit tests for exceptions.py - Custom exception classes."""

import pytest
from src.core.exceptions import (
    OrchestratorError,
    ConfigurationError,
    APIKeyError,
    ModelNotFoundError,
    TemplateNotFoundError,
    APIError,
    OpenRouterAPIError,
    LMStudioAPIError,
    RateLimitError,
    ToolExecutionError,
    FileToolError,
    ValidationError,
    TaskExecutionError,
    EscalationRequiredError,
    BudgetExceededError,
)


class TestOrchestratorError:
    """Tests for OrchestratorError base class."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        error = OrchestratorError("Test error message")
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.context == {}

    def test_exception_with_context(self):
        """Test exception with context dictionary."""
        context = {"task": "test", "tier": "L0"}
        error = OrchestratorError("Error occurred", context=context)
        assert error.context == context

    def test_to_dict(self):
        """Test conversion to dictionary."""
        context = {"key": "value"}
        error = OrchestratorError("Test message", context=context)
        result = error.to_dict()

        assert result["type"] == "OrchestratorError"
        assert result["message"] == "Test message"
        assert result["context"] == context

    def test_exception_inheritance(self):
        """Test that it inherits from Exception."""
        error = OrchestratorError("Test")
        assert isinstance(error, Exception)


class TestConfigurationError:
    """Tests for ConfigurationError class."""

    def test_basic_configuration_error(self):
        """Test basic configuration error."""
        error = ConfigurationError("Config is invalid")
        assert str(error) == "Config is invalid"
        assert isinstance(error, OrchestratorError)

    def test_configuration_error_with_context(self):
        """Test configuration error with context."""
        context = {"config_file": "missing.toml"}
        error = ConfigurationError("File not found", context=context)
        assert error.context == context


class TestAPIKeyError:
    """Tests for APIKeyError class."""

    def test_api_key_missing(self):
        """Test missing API key error."""
        error = APIKeyError("API key is required")
        assert isinstance(error, ConfigurationError)
        assert isinstance(error, OrchestratorError)

    def test_api_key_invalid(self):
        """Test invalid API key error."""
        error = APIKeyError("Invalid API key format")
        assert error.message == "Invalid API key format"


class TestModelNotFoundError:
    """Tests for ModelNotFoundError class."""

    def test_model_not_found(self):
        """Test model not found error."""
        error = ModelNotFoundError("Model 'xyz-123' not found")
        assert isinstance(error, ConfigurationError)
        assert "xyz-123" in str(error)


class TestTemplateNotFoundError:
    """Tests for TemplateNotFoundError class."""

    def test_template_not_found(self):
        """Test template not found error."""
        error = TemplateNotFoundError("Template 'missing.md' not found")
        assert isinstance(error, ConfigurationError)
        assert "missing.md" in str(error)


class TestAPIError:
    """Tests for APIError class."""

    def test_basic_api_error(self):
        """Test basic API error."""
        error = APIError("API request failed")
        assert error.message == "API request failed"
        assert error.status_code is None
        assert error.response is None

    def test_api_error_with_status_code(self):
        """Test API error with status code."""
        error = APIError("Bad request", status_code=400)
        assert error.status_code == 400

    def test_api_error_with_response(self):
        """Test API error with response."""
        response_data = '{"error": "Invalid request"}'
        error = APIError("API error", response=response_data)
        assert error.response == response_data

    def test_api_error_with_context(self):
        """Test API error with context."""
        context = {"endpoint": "/api/v1/chat"}
        error = APIError("Request failed", context=context)
        assert error.context == context

    def test_api_error_to_dict(self):
        """Test API error to_dict includes extra fields."""
        error = APIError(
            "Service unavailable",
            status_code=503,
            response="Server error",
            context={"retry": True}
        )
        result = error.to_dict()

        assert result["type"] == "APIError"
        assert result["status_code"] == 503
        assert result["response"] == "Server error"
        assert result["context"] == {"retry": True}


class TestOpenRouterAPIError:
    """Tests for OpenRouterAPIError class."""

    def test_openrouter_error(self):
        """Test OpenRouter API error."""
        error = OpenRouterAPIError("OpenRouter API failed")
        assert isinstance(error, APIError)
        assert isinstance(error, OrchestratorError)


class TestLMStudioAPIError:
    """Tests for LMStudioAPIError class."""

    def test_lmstudio_error(self):
        """Test LM Studio API error."""
        error = LMStudioAPIError("LM Studio connection failed")
        assert isinstance(error, APIError)


class TestRateLimitError:
    """Tests for RateLimitError class."""

    def test_rate_limit_error(self):
        """Test rate limit error."""
        error = RateLimitError("Rate limit exceeded")
        assert isinstance(error, APIError)
        assert "rate limit" in str(error).lower()

    def test_rate_limit_with_retry_after(self):
        """Test rate limit error with retry information."""
        error = RateLimitError(
            "Too many requests",
            status_code=429,
            context={"retry_after": 60}
        )
        assert error.status_code == 429
        assert error.context["retry_after"] == 60


class TestToolExecutionError:
    """Tests for ToolExecutionError class."""

    def test_tool_execution_error(self):
        """Test tool execution error."""
        error = ToolExecutionError("Tool execution failed")
        assert isinstance(error, OrchestratorError)
        assert "tool" in str(error).lower()

    def test_tool_execution_with_context(self):
        """Test tool execution error with context."""
        context = {"tool": "file_read", "path": "/test.txt"}
        error = ToolExecutionError("Failed to execute tool", context=context)
        assert error.context["tool"] == "file_read"


class TestFileToolError:
    """Tests for FileToolError class."""

    def test_file_read_error(self):
        """Test file read error."""
        error = FileToolError("Failed to read file")
        assert isinstance(error, ToolExecutionError)

    def test_file_write_error(self):
        """Test file write error."""
        error = FileToolError("Failed to write file")
        assert "write" in str(error).lower()


class TestValidationError:
    """Tests for ValidationError class."""

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError("Validation failed: Invalid input")
        assert isinstance(error, OrchestratorError)
        assert "validation" in str(error).lower()


class TestTaskExecutionError:
    """Tests for TaskExecutionError class."""

    def test_task_execution_error(self):
        """Test task execution error."""
        error = TaskExecutionError("Task failed after all retries")
        assert isinstance(error, OrchestratorError)

    def test_task_execution_with_tier_info(self):
        """Test task execution error with tier context."""
        context = {"last_tier": "L3", "attempts": 5}
        error = TaskExecutionError("Max retries exceeded", context=context)
        assert error.context["last_tier"] == "L3"


class TestEscalationRequiredError:
    """Tests for EscalationRequiredError class."""

    def test_escalation_required(self):
        """Test escalation required error."""
        error = EscalationRequiredError("Need to escalate to L2")
        assert isinstance(error, OrchestratorError)
        assert "escalate" in str(error).lower()

    def test_escalation_with_target_tier(self):
        """Test escalation error with target tier."""
        context = {"current_tier": "L1", "target_tier": "L2"}
        error = EscalationRequiredError("Escalate to L2", context=context)
        assert error.context["target_tier"] == "L2"


class TestBudgetExceededError:
    """Tests for BudgetExceededError class."""

    def test_budget_exceeded(self):
        """Test budget exceeded error."""
        error = BudgetExceededError("Daily budget limit reached")
        assert isinstance(error, OrchestratorError)
        assert "budget" in str(error).lower()

    def test_budget_with_amount(self):
        """Test budget exceeded with amount context."""
        context = {"daily_limit": 10.00, "spent": 10.50}
        error = BudgetExceededError("Budget exceeded", context=context)
        assert error.context["daily_limit"] == 10.00
        assert error.context["spent"] == 10.50


class TestExceptionHierarchy:
    """Tests for exception inheritance and relationships."""

    def test_configuration_error_chain(self):
        """Test ConfigurationError inheritance chain."""
        error = ConfigurationError("Test")
        assert isinstance(error, ConfigurationError)
        assert isinstance(error, OrchestratorError)
        assert isinstance(error, Exception)

    def test_api_error_chain(self):
        """Test APIError inheritance chain."""
        error = APIError("Test")
        assert isinstance(error, APIError)
        assert isinstance(error, OrchestratorError)
        assert isinstance(error, Exception)

    def test_openrouter_api_error_chain(self):
        """Test OpenRouterAPIError inheritance chain."""
        error = OpenRouterAPIError("Test")
        assert isinstance(error, OpenRouterAPIError)
        assert isinstance(error, APIError)
        assert isinstance(error, OrchestratorError)

    def test_file_tool_error_chain(self):
        """Test FileToolError inheritance chain."""
        error = FileToolError("Test")
        assert isinstance(error, FileToolError)
        assert isinstance(error, ToolExecutionError)
        assert isinstance(error, OrchestratorError)


class TestExceptionToDict:
    """Tests for exception to_dict functionality."""

    def test_error_to_dict_basic(self):
        """Test basic to_dict output."""
        error = OrchestratorError("Simple error")
        result = error.to_dict()

        assert "type" in result
        assert "message" in result
        assert "context" in result

    def test_api_error_to_dict_complete(self):
        """Test APIError to_dict with all fields."""
        error = APIError(
            "Request failed",
            status_code=500,
            response="Internal server error",
            context={"endpoint": "/api/chat"}
        )
        result = error.to_dict()

        assert result["type"] == "APIError"
        assert result["message"] == "Request failed"
        assert result["status_code"] == 500
        assert result["response"] == "Internal server error"
        assert result["context"] == {"endpoint": "/api/chat"}

    def test_error_to_dict_empty_context(self):
        """Test to_dict with empty context."""
        error = ConfigurationError("Config error")
        result = error.to_dict()

        assert result["context"] == {}


class TestExceptionUsagePatterns:
    """Tests for common exception usage patterns."""

    def test_catch_base_exception(self):
        """Test catching base OrchestratorError."""
        try:
            raise OrchestratorError("Test error")
        except OrchestratorError as e:
            assert str(e) == "Test error"

    def test_catch_specific_exception(self):
        """Test catching specific exception type."""
        try:
            raise APIKeyError("Key not found")
        except APIKeyError as e:
            assert "key" in str(e).lower()

    def test_catch_base_class(self):
        """Test catching base class catches derived exceptions."""
        try:
            raise RateLimitError("Rate limited")
        except APIError as e:
            assert "rate" in str(e).lower()

    def test_exception_with_reraise(self):
        """Test exception logging and re-raise."""
        try:
            try:
                raise ModelNotFoundError("Model not found")
            except ModelNotFoundError:
                raise APIError("Wrapper error") from None
        except APIError as e:
            assert e.status_code is None
