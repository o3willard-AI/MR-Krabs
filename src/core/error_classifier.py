#!/usr/bin/env python3
"""Error classification and user-facing error messages.

Maps raw exceptions to actionable categories with user-facing messages
that explain what happened, why, and what to do about it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    CONTEXT = "context"
    MODEL_CAPABILITY = "model_capability"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    INFRASTRUCTURE = "infrastructure"
    BUDGET = "budget"
    CIRCUIT_BREAKER = "circuit_breaker"
    TIMEOUT = "timeout"


class ErrorAction(Enum):
    RETRY = "retry"
    RETRY_WITH_DELAY = "retry_delay"
    RETRY_SIMPLIFIED = "retry_simplified"
    ESCALATE = "escalate"
    FAIL = "fail"
    SWITCH_PROVIDER = "switch_provider"


ERROR_CLASSIFICATION: dict[str, tuple[ErrorCategory, ErrorAction]] = {
    "ConnectionError": (ErrorCategory.TRANSIENT, ErrorAction.RETRY),
    "TimeoutError": (ErrorCategory.TIMEOUT, ErrorAction.RETRY_WITH_DELAY),
    "ConnectionRefusedError": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "ConnectionResetError": (ErrorCategory.TRANSIENT, ErrorAction.RETRY),
    "SSLError": (ErrorCategory.INFRASTRUCTURE, ErrorAction.RETRY_WITH_DELAY),
    "RateLimitError": (ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    "ContextLengthExceeded": (ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    "ContextWindowExceeded": (ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    "ModelCapabilityError": (ErrorCategory.MODEL_CAPABILITY, ErrorAction.ESCALATE),
    "ValidationError": (ErrorCategory.VALIDATION, ErrorAction.RETRY_SIMPLIFIED),
    "AuthenticationError": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    "PermissionError": (ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    "BudgetExceededError": (ErrorCategory.BUDGET, ErrorAction.FAIL),
    "CircuitOpenError": (ErrorCategory.CIRCUIT_BREAKER, ErrorAction.SWITCH_PROVIDER),
}

ERROR_MESSAGE_PATTERNS: list[tuple[str, ErrorCategory, ErrorAction]] = [
    (r"(?i)rate\s*limit", ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    (r"(?i)429", ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY),
    (r"(?i)context\s*length\s*exceeded", ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    (r"(?i)context\s*window", ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    (r"(?i)token\s*limit", ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    (r"(?i)max\s*token", ErrorCategory.CONTEXT, ErrorAction.RETRY_SIMPLIFIED),
    (
        r"(?i)model.*(not\s*(found|available|supported)|deprecated)",
        ErrorCategory.MODEL_CAPABILITY,
        ErrorAction.ESCALATE,
    ),
    (r"(?i)invalid\s*(api\s*)?key", ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    (r"(?i)unauthorized", ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    (r"(?i)forbidden", ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    (r"(?i)401", ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    (r"(?i)403", ErrorCategory.AUTHENTICATION, ErrorAction.FAIL),
    (r"(?i)budget\s*exceeded", ErrorCategory.BUDGET, ErrorAction.FAIL),
    (r"(?i)circuit\s*(is\s*)?open", ErrorCategory.CIRCUIT_BREAKER, ErrorAction.SWITCH_PROVIDER),
    (r"(?i)connection\s*(refused|reset|timed?\s*out)", ErrorCategory.TRANSIENT, ErrorAction.RETRY),
    (r"(?i)5\d{2}", ErrorCategory.TRANSIENT, ErrorAction.RETRY),
]

USER_FACING_MESSAGES: dict[ErrorCategory, dict[str, str]] = {
    ErrorCategory.TRANSIENT: {
        "what": "A temporary error occurred while calling the LLM provider.",
        "why": "This is usually caused by network issues or a brief provider outage.",
        "fix": "The system will retry automatically. If this persists, check your network connection and the provider's status page.",
    },
    ErrorCategory.RATE_LIMIT: {
        "what": "You have been rate-limited by the LLM provider.",
        "why": "Too many requests were sent in a short time period.",
        "fix": "The system will retry after a delay. Consider reducing concurrency or increasing the time between requests.",
    },
    ErrorCategory.CONTEXT: {
        "what": "The context (prompt) is too long for this model.",
        "why": "The model has a maximum context window that was exceeded.",
        "fix": "The system will automatically simplify the context and retry. If this persists, try a model with a larger context window or reduce your input.",
    },
    ErrorCategory.MODEL_CAPABILITY: {
        "what": "This model cannot handle the requested task.",
        "why": "The model may not support the required features (tool calling, specific format, etc.).",
        "fix": "The system will escalate to a more capable model. You can also configure a different model for this tier.",
    },
    ErrorCategory.VALIDATION: {
        "what": "The model's output did not pass validation.",
        "why": "The response may be incomplete, malformed, or missing required elements.",
        "fix": "The system will retry with a simplified context. Check that your task description is clear and specific.",
    },
    ErrorCategory.AUTHENTICATION: {
        "what": "Authentication failed with the LLM provider.",
        "why": "Your API key may be invalid, expired, or missing required permissions.",
        "fix": "Verify your API key is correct and has not expired. Set it with: export OPENROUTER_API_KEY='your-key'",
    },
    ErrorCategory.INFRASTRUCTURE: {
        "what": "An infrastructure error occurred (network, DNS, SSL, etc.).",
        "why": "This may be caused by network configuration, firewall rules, or provider infrastructure issues.",
        "fix": "Check your network connection, firewall settings, and DNS configuration. Retry after a delay.",
    },
    ErrorCategory.BUDGET: {
        "what": "Your budget limit has been reached.",
        "why": "The total spending has exceeded your configured daily/weekly/monthly limit.",
        "fix": "Options: (1) Wait for the budget period to reset, (2) Increase your budget limit in config, (3) Set budget.failure_mode to 'fail_open_with_alert' for a grace period.",
    },
    ErrorCategory.CIRCUIT_BREAKER: {
        "what": "The circuit breaker is open for this provider/model.",
        "why": "Too many recent failures have triggered the circuit breaker to prevent further wasted calls.",
        "fix": "The system will automatically switch to a fallback provider. The circuit will reset after the cooldown period.",
    },
    ErrorCategory.TIMEOUT: {
        "what": "The LLM request timed out.",
        "why": "The provider took too long to respond, possibly due to high load or a complex request.",
        "fix": "The system will retry with a longer timeout. Consider simplifying your request or using a faster model.",
    },
}


@dataclass
class ClassifiedError:
    """A classified error with user-facing message."""

    category: ErrorCategory
    action: ErrorAction
    original_error: Exception | None = None
    user_message: str = ""
    technical_details: str = ""

    def format_user_message(self) -> str:
        """Format the full user-facing error message."""
        msg = USER_FACING_MESSAGES.get(self.category, {})
        parts = [
            f"Error: {msg.get('what', 'An unknown error occurred.')}",
            f"Reason: {msg.get('why', 'Unknown reason.')}",
            f"What to do: {msg.get('fix', 'No specific guidance available.')}",
        ]
        if self.technical_details:
            parts.append(f"Details: {self.technical_details}")
        return "\n".join(parts)


class FailureAnalyzer:
    """Classifies errors into categories and recommends actions."""

    def analyze(self, error: Exception) -> ClassifiedError:
        """Analyze an error and return a classified result."""
        error_type = type(error).__name__
        error_str = str(error)
        http_status = self._extract_http_status(error_str)

        category, action = self._classify(error_type, error_str, http_status)

        return ClassifiedError(
            category=category,
            action=action,
            original_error=error,
            technical_details=f"{error_type}: {error_str}",
        )

    def _classify(
        self,
        error_type: str,
        error_message: str,
        http_status: int | None = None,
    ) -> tuple[ErrorCategory, ErrorAction]:
        """Classify error using 4-step strategy."""
        if error_type in ERROR_CLASSIFICATION:
            return ERROR_CLASSIFICATION[error_type]

        for pattern, category, action in ERROR_MESSAGE_PATTERNS:
            if re.search(pattern, error_message):
                return category, action

        if http_status is not None:
            if http_status == 429:
                return ErrorCategory.RATE_LIMIT, ErrorAction.RETRY_WITH_DELAY
            if http_status in (401, 403):
                return ErrorCategory.AUTHENTICATION, ErrorAction.FAIL
            if http_status >= 500:
                return ErrorCategory.TRANSIENT, ErrorAction.RETRY

        return ErrorCategory.TRANSIENT, ErrorAction.ESCALATE

    def _extract_http_status(self, error_message: str) -> int | None:
        """Extract HTTP status code from error message."""
        match = re.search(r"(?<!\d)([45]\d{2})(?!\d)", error_message)
        if match:
            return int(match.group(1))
        return None
