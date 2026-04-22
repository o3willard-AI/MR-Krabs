#!/usr/bin/env python3
"""Custom exceptions for Multi-Tier Orchestrator."""


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary for logging."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "context": self.context
        }


class ConfigurationError(OrchestratorError):
    """Configuration-related errors."""
    pass


class APIKeyError(ConfigurationError):
    """API key missing or invalid."""
    pass


class ModelNotFoundError(ConfigurationError):
    """Model ID not found or invalid."""
    pass


class TemplateNotFoundError(ConfigurationError):
    """Prompt template file not found."""
    pass


class APIError(OrchestratorError):
    """External API errors."""
    def __init__(self, message: str, status_code: int = None, response: str = None, context: dict = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message, context)
    
    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "status_code": self.status_code,
            "response": self.response
        }


class OpenRouterAPIError(APIError):
    """OpenRouter API errors."""
    pass


class LMStudioAPIError(APIError):
    """LM Studio API errors."""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""
    pass


class ToolExecutionError(OrchestratorError):
    """Tool execution failed."""
    pass


class FileToolError(ToolExecutionError):
    """File read/write operation failed."""
    pass


class ValidationError(OrchestratorError):
    """Validation failed."""
    pass


class TaskExecutionError(OrchestratorError):
    """Task execution failed after all retries."""
    pass


class EscalationRequiredError(OrchestratorError):
    """Task requires escalation to next tier."""
    pass
