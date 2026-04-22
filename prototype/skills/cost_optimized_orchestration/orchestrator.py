#!/usr/bin/env python3
"""Cost-Optimized Orchestrator - Core implementation."""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TierConfig:
    """Configuration for a single tier."""
    name: str
    model: str
    provider: str
    base_url: str
    temperature: float = 0.7
    tools: List[str] = field(default_factory=list)
    env_var: Optional[str] = None
    cost_per_million_prompt: float = 0.001
    cost_per_million_completion: float = 0.001
    max_retries: int = 3
    retry_delay: int = 2
    
    def get_api_key(self) -> Optional[str]:
        """Get API key from environment."""
        if self.env_var:
            return os.environ.get(self.env_var)
        return None
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for token usage."""
        prompt_cost = (prompt_tokens / 1_000_000) * self.cost_per_million_prompt
        completion_cost = (completion_tokens / 1_000_000) * self.cost_per_million_completion
        return prompt_cost + completion_cost


@dataclass
class ExecutionResult:
    """Result of a task execution attempt."""
    task_id: str
    tier: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    attempts: int = 1
    duration_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    ready_for_escalation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CostOptimizedOrchestrator:
    """Orchestrates tasks across cost-optimized tiers."""
    
    # Default tier configuration (matching original orchestrator)
    DEFAULT_TIERS = {
        "L0-Planner": TierConfig(
            name="L0-Planner",
            model="qwen/qwen3.5-397b-a17b",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.3,
            tools=["file_read"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.001,
            cost_per_million_completion=0.001
        ),
        "L0-Reviewer": TierConfig(
            name="L0-Reviewer",
            model="qwen/qwen3.5-397b-a17b",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.3,
            tools=["file_read"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.001,
            cost_per_million_completion=0.001
        ),
        "L0-Coder": TierConfig(
            name="L0-Coder",
            model="qwen/qwen3-coder-30b",
            provider="lmstudio",
            base_url="http://192.168.101.21:1234/v1",
            temperature=0.7,
            tools=["file_read", "file_write"],
            cost_per_million_prompt=0.0,  # Local model
            cost_per_million_completion=0.0
        ),
        "L1-Coder": TierConfig(
            name="L1-Coder",
            model="x-ai/grok-4.1-fast",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
            tools=["file_read", "file_write"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.002,
            cost_per_million_completion=0.006
        ),
        "L2-Coder": TierConfig(
            name="L2-Coder",
            model="minimax/minimax-m2.7",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
            tools=["file_read", "file_write"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.0002,
            cost_per_million_completion=0.0006
        ),
        "L3-Coder": TierConfig(
            name="L3-Coder",
            model="anthropic/claude-sonnet-4.6",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
            tools=["file_read", "file_write"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.003,
            cost_per_million_completion=0.015
        ),
        "L3-Architect": TierConfig(
            name="L3-Architect",
            model="anthropic/claude-opus-4.6",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            temperature=0.3,
            tools=["file_read"],
            env_var="OPENROUTER_API_KEY",
            cost_per_million_prompt=0.015,
            cost_per_million_completion=0.075
        )
    }
    
    # Context simplification multipliers for retries
    CONTEXT_SIMPLIFICATION = [1.0, 0.7, 0.4]
    
    def __init__(
        self,
        tiers: Optional[Dict[str, TierConfig]] = None,
        budget_daily_usd: float = 10.0,
        project_root: str = ".",
        llm_caller: Optional[Callable] = None
    ):
        """
        Initialize orchestrator.
        
        Args:
            tiers: Custom tier configuration
            budget_daily_usd: Daily budget limit in USD
            project_root: Root directory for file operations
            llm_caller: Function to call LLM (for framework integration)
        """
        self.tiers = tiers or self.DEFAULT_TIERS
        self.budget_daily_usd = budget_daily_usd
        self.project_root = Path(project_root)
        self.llm_caller = llm_caller or self._default_llm_caller
        
        # Tracking
        self.total_cost = 0.0
        self.execution_history: List[ExecutionResult] = []
        self.failure_logs = []
        
        # Create directories
        self.logs_dir = self.project_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized CostOptimizedOrchestrator with {len(self.tiers)} tiers")
        logger.info(f"Daily budget: ${budget_daily_usd:.2f}")
    
    def _default_llm_caller(
        self,
        tier: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float
    ) -> str:
        """
        Default LLM caller (simplified version).
        In practice, this would integrate with actual LLM providers.
        """
        # This is a placeholder - real implementation would call APIs
        logger.warning(f"Using default LLM caller for {tier} - implement with actual provider")
        
        # Simulate API call
        time.sleep(0.5)
        
        # Return mock response based on tier
        tier_config = self.tiers[tier]
        if "coder" in tier.lower():
            return f"# Implementation by {tier}\n\n```python\n# Code would be here\nprint('Hello from {tier}')\n```"
        elif "planner" in tier.lower():
            return f"# Plan by {tier}\n\n1. Analyze requirements\n2. Design architecture\n3. Implement components\n4. Test and validate"
        elif "reviewer" in tier.lower():
            return f"# Review by {tier}\n\n✅ Code follows best practices\n✅ All requirements met\n✅ Tests pass"
        else:
            return f"Response from {tier}: Task completed successfully."
    
    def _simplify_context(self, prompt: str, multiplier: float) -> str:
        """Simplify prompt by truncating (matching original logic)."""
        if multiplier >= 1.0:
            return prompt
        
        lines = prompt.splitlines()
        max_lines = max(int(len(lines) * multiplier), 10)
        simplified = '\n'.join(lines[:max_lines])
        
        logger.debug(f"Simplified context from {len(lines)} to {max_lines} lines")
        return simplified + f"\n\n[Context truncated from {len(lines)} to {max_lines} lines]"
    
    def _call_llm_with_retry(
        self,
        tier: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float
    ) -> Dict[str, Any]:
        """Call LLM with retry logic and context simplification."""
        tier_config = self.tiers[tier]
        last_error = None
        
        for attempt in range(tier_config.max_retries):
            try:
                # Simplify context on retries
                multiplier = self.CONTEXT_SIMPLIFICATION[
                    min(attempt, len(self.CONTEXT_SIMPLIFICATION) - 1)
                ]
                prompt = self._simplify_context(user_prompt, multiplier) if attempt > 0 else user_prompt
                
                start_time = time.time()
                response = self.llm_caller(tier, system_prompt, prompt, temperature)
                duration = time.time() - start_time
                
                # Estimate token usage (simplified)
                # In practice, get actual counts from API response
                prompt_tokens = len(system_prompt + prompt) // 4  # Rough estimate
                completion_tokens = len(response) // 4
                cost = tier_config.estimate_cost(prompt_tokens, completion_tokens)
                
                # Check budget
                self.total_cost += cost
                if self.total_cost > self.budget_daily_usd:
                    raise BudgetExceededError(
                        f"Daily budget exceeded: ${self.total_cost:.4f} / ${self.budget_daily_usd:.2f}"
                    )
                
                return {
                    "success": True,
                    "output": response,
                    "attempt": attempt + 1,
                    "duration_seconds": duration,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost,
                    "context_simplified": attempt > 0
                }
                
            except BudgetExceededError as e:
                raise
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1}/{tier_config.max_retries} failed: {last_error}")
                
                if attempt < tier_config.max_retries - 1:
                    logger.info(f"Retrying in {tier_config.retry_delay}s with simplified context...")
                    time.sleep(tier_config.retry_delay)
        
        return {
            "success": False,
            "error": last_error,
            "attempts": tier_config.max_retries,
            "ready_for_escalation": True
        }
    
    def _get_next_tier(self, current_tier: str) -> Optional[str]:
        """Get the next tier for escalation."""
        tier_order = ["L0-Coder", "L0-Reviewer", "L1-Coder", "L2-Coder", "L3-Coder", "L3-Architect"]
        
        if current_tier not in tier_order:
            return None
        
        current_index = tier_order.index(current_tier)
        if current_index + 1 < len(tier_order):
            return tier_order[current_index + 1]
        
        return None
    
    def execute_task(
        self,
        task_id: str,
        description: str,
        context: Dict[str, Any],
        initial_tier: str = "L0-Coder"
    ) -> ExecutionResult:
        """
        Execute a task with tiered escalation.
        
        Args:
            task_id: Unique identifier for the task
            description: Human-readable task description
            context: Additional context for the task
            initial_tier: Starting tier for execution
            
        Returns:
            ExecutionResult with outcome details
        """
        logger.info(f"Executing task {task_id}: {description}")
        logger.info(f"Starting with tier: {initial_tier}")
        
        current_tier = initial_tier
        tier_results = []
        
        while current_tier:
            tier_config = self.tiers[current_tier]
            logger.info(f"Attempting with {current_tier} ({tier_config.model})")
            
            # Build prompts (simplified - would use templates in real implementation)
            system_prompt = f"You are a {current_tier} assistant. {description}"
            user_prompt = f"Task: {description}\n\nContext:\n{json.dumps(context, indent=2)}"
            
            # Call LLM with retry logic
            result = self._call_llm_with_retry(
                tier=current_tier,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=tier_config.temperature
            )
            
            # Create execution result
            exec_result = ExecutionResult(
                task_id=task_id,
                tier=current_tier,
                success=result.get("success", False),
                output=result.get("output", ""),
                error=result.get("error"),
                attempts=result.get("attempt", result.get("attempts", 1)),
                duration_seconds=result.get("duration_seconds", 0.0),
                prompt_tokens=result.get("prompt_tokens", 0),
                completion_tokens=result.get("completion_tokens", 0),
                cost_usd=result.get("cost_usd", 0.0),
                ready_for_escalation=result.get("ready_for_escalation", False),
                metadata={
                    "context_simplified": result.get("context_simplified", False),
                    "model": tier_config.model
                }
            )
            
            tier_results.append(exec_result)
            self.execution_history.append(exec_result)
            
            # Log result
            self._log_execution(exec_result)
            
            if exec_result.success:
                logger.info(f"✓ Task {task_id} completed by {current_tier}")
                logger.info(f"  Cost: ${exec_result.cost_usd:.4f}, Duration: {exec_result.duration_seconds:.1f}s")
                return exec_result
            else:
                logger.warning(f"✗ Task {task_id} failed with {current_tier}: {exec_result.error}")
                
                # Get next tier for escalation
                next_tier = self._get_next_tier(current_tier)
                if next_tier and exec_result.ready_for_escalation:
                    logger.info(f"Escalating from {current_tier} to {next_tier}")
                    current_tier = next_tier
                else:
                    logger.error(f"No further escalation available for task {task_id}")
                    break
        
        # If we get here, all tiers failed
        final_result = tier_results[-1] if tier_results else ExecutionResult(
            task_id=task_id,
            tier=initial_tier,
            success=False,
            error="All tiers failed"
        )
        
        logger.error(f"Task {task_id} failed across all tiers")
        return final_result
    
    def _log_execution(self, result: ExecutionResult):
        """Log execution result to file."""
        timestamp = datetime.now(timezone.utc).isoformat().replace(':', '-')
        log_file = self.logs_dir / f"{result.task_id}_{result.tier}_{timestamp}.json"
        
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "task_id": result.task_id,
            "tier": result.tier,
            "success": result.success,
            "attempts": result.attempts,
            "duration_seconds": result.duration_seconds,
            "cost_usd": result.cost_usd,
            "total_tokens": result.total_tokens,
            "error": result.error,
            "metadata": result.metadata
        }
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.debug(f"Logged execution to {log_file}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all executions."""
        total_tasks = len(self.execution_history)
        successful = sum(1 for r in self.execution_history if r.success)
        failed = total_tasks - successful
        
        tier_breakdown = {}
        for tier in self.tiers:
            tier_execs = [r for r in self.execution_history if r.tier == tier]
            if tier_execs:
                tier_breakdown[tier] = {
                    "count": len(tier_execs),
                    "successful": sum(1 for r in tier_execs if r.success),
                    "total_cost": sum(r.cost_usd for r in tier_execs),
                    "avg_duration": sum(r.duration_seconds for r in tier_execs) / len(tier_execs) if tier_execs else 0
                }
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful,
            "failed_tasks": failed,
            "success_rate": successful / total_tasks if total_tasks > 0 else 0,
            "total_cost_usd": self.total_cost,
            "budget_remaining_usd": max(0, self.budget_daily_usd - self.total_cost),
            "tier_breakdown": tier_breakdown,
            "execution_history": [
                {
                    "task_id": r.task_id,
                    "tier": r.tier,
                    "success": r.success,
                    "cost": r.cost_usd,
                    "duration": r.duration_seconds
                }
                for r in self.execution_history[-10:]  # Last 10 executions
            ]
        }
    
    def reset_budget(self):
        """Reset budget tracking (e.g., at start of new day)."""
        self.total_cost = 0.0
        logger.info("Budget tracking reset")


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""
    pass


# Simple CLI for testing
def main():
    """Test the orchestrator with a simple task."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test CostOptimizedOrchestrator")
    parser.add_argument("--task", default="test_task", help="Task ID")
    parser.add_argument("--description", default="Write a hello world function", help="Task description")
    parser.add_argument("--tier", default="L0-Coder", choices=["L0-Coder", "L1-Coder", "L2-Coder", "L3-Coder"], help="Initial tier")
    parser.add_argument("--budget", type=float, default=10.0, help="Daily budget in USD")
    
    args = parser.parse_args()
    
    # Create orchestrator
    orchestrator = CostOptimizedOrchestrator(budget_daily_usd=args.budget)
    
    # Execute task
    context = {
        "language": "Python",
        "requirements": "Function should print 'Hello, World!'",
        "testing": "Include a test"
    }
    
    print(f"Executing task: {args.task}")
    print(f"Description: {args.description}")
    print(f"Initial tier: {args.tier}")
    print(f"Budget: ${args.budget:.2f}")
    print("-" * 50)
    
    result = orchestrator.execute_task(
        task_id=args.task,
        description=args.description,
        context=context,
        initial_tier=args.tier
    )
    
    print("\n" + "=" * 50)
    print("RESULT:")
    print(f"Success: {result.success}")
    print(f"Final tier: {result.tier}")
    print(f"Attempts: {result.attempts}")
    print(f"Cost: ${result.cost_usd:.4f}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    
    if result.success:
        print(f"\nOutput preview:\n{result.output[:200]}...")
    else:
        print(f"\nError: {result.error}")
    
    # Print summary
    summary = orchestrator.get_summary()
    print(f"\nSummary:")
    print(f"Total cost: ${summary['total_cost_usd']:.4f}")
    print(f"Budget remaining: ${summary['budget_remaining_usd']:.4f}")
    print(f"Success rate: {summary['success_rate']:.1%}")
    
    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())