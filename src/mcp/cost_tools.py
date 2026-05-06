"""
Cost Management Tools for MR-Krabs MCP Server

Implements cost estimation, budget checking, and cost tracking tools.
Supports both stateful (session-based) and stateless operation modes.

Tools:
- mcp_mrkrabs_cost_estimate: Estimate cost for LLM usage
- mcp_mrkrabs_budget_check: Check remaining budget and enforce limits
- mcp_mrkrabs_cost_track: Record actual spending
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time

# Cost estimation rates per 1K tokens (in USD) - Example rates
COST_RATES = {
    "google/gemma-7b-it": {"input": 0.0001, "output": 0.0001},
    "google/gemma-2b-it": {"input": 0.000075, "output": 0.000075},
    "meta-llama/llama-3-8b-instruct": {"input": 0.00003, "output": 0.00003},
    "meta-llama/llama-3-70b-instruct": {"input": 0.000059, "output": 0.000079},
    "mistralai/mistral-7b-instruct": {"input": 0.00016, "output": 0.00016},
    "default": {"input": 0.00025, "output": 0.00025},  # Conservative default
}


@dataclass
class CostBreakdown:
    """Detailed cost breakdown."""
    estimated_cost: float
    input_tokens: int
    output_tokens: int
    model: str
    rate_per_1k_input: float
    rate_per_1k_output: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_cost": self.estimated_cost,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "rate_per_1k_input": self.rate_per_1k_input,
            "rate_per_1k_output": self.rate_per_1k_output,
        }


def estimate_cost(
    model: str = "default",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    prompt_text: Optional[str] = None,
) -> CostBreakdown:
    """
    Estimate cost for LLM usage.
    
    Args:
        model: Model identifier (e.g., "google/gemma-7b-it")
        input_tokens: Number of input tokens (optional)
        output_tokens: Number of output tokens (optional)
        prompt_text: Prompt text to estimate tokens from (optional)
    
    Returns:
        CostBreakdown with detailed cost information
    
    Notes:
        - If prompt_text provided but no token count, estimate ~4 chars per token
        - Uses conservative default rates if model not found
    """
    # Get rate for model
    if model in COST_RATES:
        rate_input = COST_RATES[model]["input"]
        rate_output = COST_RATES[model]["output"]
    else:
        rate_input = COST_RATES["default"]["input"]
        rate_output = COST_RATES["default"]["output"]
    
    # Estimate tokens from text if provided
    if prompt_text and not input_tokens:
        # Rough estimate: ~4 characters per token
        input_tokens = len(prompt_text) // 4
    
    # Use defaults if not specified
    input_tokens = input_tokens or 0
    output_tokens = output_tokens or 0
    
    # Calculate cost (rates are per 1K tokens)
    cost = (input_tokens / 1000) * rate_input + (output_tokens / 1000) * rate_output
    
    return CostBreakdown(
        estimated_cost=round(cost, 6),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        rate_per_1k_input=rate_input,
        rate_per_1k_output=rate_output,
    )


class CostEstimateRequest(BaseModel):
    """Request model for cost estimation."""
    session_id: Optional[str] = Field(None, description="Session ID (optional)")
    config: Optional[Dict[str, Any]] = Field(None, description="Full config for stateless mode")
    model: str = Field(default="default", description="LLM model identifier")
    input_tokens: Optional[int] = Field(None, description="Number of input tokens")
    output_tokens: Optional[int] = Field(None, description="Expected output tokens")
    prompt_text: Optional[str] = Field(None, description="Prompt text for token estimation")


class CostEstimateResponse(BaseModel):
    """Response model for cost estimation."""
    estimated_cost: float
    breakdown: Dict[str, Any]
    session_id: Optional[str] = None
    warning: Optional[str] = None


def process_cost_estimate(request: CostEstimateRequest) -> CostEstimateResponse:
    """
    Process cost estimation request.
    
    Args:
        request: CostEstimateRequest with model and token information
    
    Returns:
        CostEstimateResponse with cost estimate
    """
    # Estimate cost
    breakdown = estimate_cost(
        model=request.model,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        prompt_text=request.prompt_text,
    )
    
    return CostEstimateResponse(
        estimated_cost=breakdown.estimated_cost,
        breakdown=breakdown.to_dict(),
        session_id=request.session_id,
        warning=None,  # Will be set by budget check if needed
    )


# ==================== Budget Check Tools ====================

@dataclass
class BudgetStatus:
    """Current budget status."""
    remaining_budget: float
    spent: float
    budget_limit: Optional[float]
    percentage_used: float
    can_proceed: bool
    warning: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "remaining_budget": self.remaining_budget,
            "spent": self.spent,
            "budget_limit": self.budget_limit,
            "percentage_used": self.percentage_used,
            "can_proceed": self.can_proceed,
            "warning": self.warning,
            "error": self.error,
        }


class BudgetCheckRequest(BaseModel):
    """Request model for budget checking."""
    session_id: Optional[str] = Field(None, description="Session ID (optional)")
    config: Optional[Dict[str, Any]] = Field(None, description="Full config for stateless mode")
    would_spend: float = Field(description="Amount that would be spent")


class BudgetCheckResponse(BaseModel):
    """Response model for budget checking."""
    can_proceed: bool
    status: Dict[str, Any]
    session_id: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None


# ==================== Cost Tracking Tools ====================

@dataclass
class CostRecord:
    """Record of actual cost."""
    amount: float
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "timestamp": self.timestamp,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)),
        }


class CostTrackRequest(BaseModel):
    """Request model for cost tracking."""
    session_id: Optional[str] = Field(None, description="Session ID (optional)")
    config: Optional[Dict[str, Any]] = Field(None, description="Full config for stateless mode")
    amount: float = Field(description="Actual amount spent")
    model: str = Field(default="default", description="LLM model used")
    input_tokens: int = Field(default=0, description="Input tokens used")
    output_tokens: int = Field(default=0, description="Output tokens generated")


class CostTrackResponse(BaseModel):
    """Response model for cost tracking."""
    recorded: bool
    record: Dict[str, Any]
    session_id: Optional[str] = None
    message: str


def process_cost_track(request: CostTrackRequest) -> CostTrackResponse:
    """
    Process cost tracking request.
    
    Args:
        request: CostTrackRequest with spending details
    
    Returns:
        CostTrackResponse confirming recording
    """
    record = CostRecord(
        amount=request.amount,
        model=request.model,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        timestamp=time.time(),
    )
    
    return CostTrackResponse(
        recorded=True,
        record=record.to_dict(),
        session_id=request.session_id,
        message=f"Cost ${request.amount:.4f} recorded for model {request.model}",
    )
