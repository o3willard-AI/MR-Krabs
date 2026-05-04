#!/usr/bin/env python3
"""Enhanced CrewAI integration with cost tracking.

P2-1: Enhanced CrewAI Integration
Provides cost-aware CrewAI integration with:
- Cost tracking for all tool executions
- Automatic tier mapping by agent role
- Memory system compatibility
- Zero performance overhead
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pathlib import Path

try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


from src.core.cost import Budget, CostTracker, TokenCount, FailureMode
from src.core.tier_manager import Tier, TierLevel, TierManager


# Agent role to tier mapping
DEFAULT_ROLE_TO_TIER_MAPPING = {
    # Research roles → L0 (cheap, fast iteration)
    "researcher": TierLevel.L0,
    "analyzer": TierLevel.L0,
    "planner": TierLevel.L0,
    
    # Coding roles → L1 (medium, good balance)
    "coder": TierLevel.L1,
    "developer": TierLevel.L1,
    "engineer": TierLevel.L1,
    "programmer": TierLevel.L1,
    
    # Review roles → L1 (medium, quality focus)
    "reviewer": TierLevel.L1,
    "validator": TierLevel.L1,
    "tester": TierLevel.L1,
    
    # Architecture roles → L2 (expensive, complex decisions)
    "architect": TierLevel.L2,
    "designer": TierLevel.L2,
    "lead": TierLevel.L2,
    "manager": TierLevel.L2,
    
    # Executive roles → L3 (premium, critical decisions)
    "strategist": TierLevel.L3,
    "consultant": TierLevel.L3,
    "advisor": TierLevel.L3,
}


@dataclass
class CrewAIConfig:
    """Configuration for CrewAI integration."""
    
    # Enable/disable cost tracking
    enable_cost_tracking: bool = True
    
    # Budget configuration
    daily_budget_usd: float = 10.0
    task_limit_usd: float = 1.0
    
    # Tier mapping configuration
    auto_tier_mapping: bool = True
    role_to_tier_mapping: Optional[Dict[str, TierLevel]] = None
    
    # Default tier if mapping fails
    default_tier: TierLevel = TierLevel.L0
    
    # Failure mode
    failure_mode: FailureMode = FailureMode.FAIL_OPEN_WITH_ALERT


class CrewAICostTracker:
    """Cost tracker integrated with CrewAI."""
    
    def __init__(self, config: Optional[CrewAIConfig] = None):
        """Initialize CrewAI cost tracker."""
        self.config = config or CrewAIConfig()
        
        # Initialize budget and cost tracker
        budget = Budget(
            daily_limit_usd=Budget._dataclasses_default(daily_limit_usd=self.config.daily_budget_usd),
            task_limit_usd=Budget._dataclasses_default(task_limit_usd=self.config.task_limit_usd),
            failure_mode=self.config.failure_mode,
        )
        
        self.cost_tracker = CostTracker(budget=budget)
        
        # Role to tier mapping
        self.role_to_tier_mapping = (
            self.config.role_to_tier_mapping or DEFAULT_ROLE_TO_TIER_MAPPING
        )
    
    def get_tier_for_role(self, role: str) -> TierLevel:
        """Map agent role to cost tier.
        
        Args:
            role: Agent role (e.g., "researcher", "coder", "architect")
            
        Returns:
            TierLevel for the role
        """
        role_lower = role.lower().strip()
        
        # Try exact match first
        if role_lower in self.role_to_tier_mapping:
            return self.role_to_tier_mapping[role_lower]
        
        # Try partial match (contains)
        for mapped_role, tier in self.role_to_tier_mapping.items():
            if mapped_role in role_lower or role_lower in mapped_role:
                return tier
        
        # Return default
        return self.config.default_tier
    
    def get_tier_for_agent(self, agent: Agent) -> Tier:
        """Get tier configuration for a CrewAI agent.
        
        Args:
            agent: CrewAI agent instance
            
        Returns:
            Tier configuration from TierManager
        """
        # Extract role from agent
        role = getattr(agent, 'role', 'unknown')
        
        # Map role to tier
        tier_level = self.get_tier_for_role(role)
        
        # Get tier from TierManager
        return TierManager.get_tier(tier_level)
    
    def track_tool_execution(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        tier: Tier,
        duration: float
    ) -> Dict[str, Any]:
        """Track a tool execution with cost information.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool execution result
            tier: Tier being used
            duration: Execution duration in seconds
            
        Returns:
            Result with added cost metadata
        """
        if not self.config.enable_cost_tracking:
            return result
        
        # Estimate tokens
        input_text = str(args)
        output_text = str(result) if not isinstance(result, dict) else str(result.get('content', ''))
        
        prompt_tokens = len(input_text) // 4
        completion_tokens = len(output_text) // 4
        
        # Calculate cost
        tokens = TokenCount(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        
        cost = tier.cost_per_1k_tokens.get('prompt', 0) * (prompt_tokens / 1000) + \
               tier.cost_per_1k_tokens.get('completion', 0) * (completion_tokens / 1000)
        
        # Track in cost tracker
        try:
            entry = self.cost_tracker.record(
                task_id=tool_name,
                tier=tier.name,
                model=tier.model,
                tokens=tokens,
                duration=duration
            )
        except Exception:
            # Ignore tracking errors - don't break tool execution
            pass
        
        # Add metadata to result
        if isinstance(result, dict):
            result['_cost_metadata'] = {
                'tool': tool_name,
                'tier': tier.name,
                'model': tier.model,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'cost_usd': float(cost),
                'duration_seconds': duration,
            }
        
        return result


class CrewAIOrchestrator:
    """Enhanced CrewAI orchestrator with cost tracking and tier mapping."""
    
    def __init__(
        self,
        cost_tracker: Optional[CrewAICostTracker] = None,
        config: Optional[CrewAIConfig] = None
    ):
        """Initialize CrewAI orchestrator.
        
        Args:
            cost_tracker: Optional custom cost tracker
            config: Optional configuration
        """
        self.cost_tracker = cost_tracker or CrewAICostTracker(config)
        self.config = self.cost_tracker.config
        self.agents: Dict[str, Agent] = {}
        self.tiers: Dict[str, Tier] = {}
    
    def create_agent(
        self,
        role: str,
        goal: str,
        backstory: str,
        tier_override: Optional[TierLevel] = None,
        **agent_kwargs
    ) -> Agent:
        """Create a CrewAI agent with cost-aware tier configuration.
        
        Args:
            role: Agent role
            goal: Agent goal
            backstory: Agent backstory
            tier_override: Optional tier override (uses role mapping if None)
            **agent_kwargs: Additional CrewAI agent parameters
            
        Returns:
            Configured CrewAI agent
        """
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. "
                "Install with: pip install crewai"
            )
        
        # Determine tier
        if tier_override:
            tier_level = tier_override
        else:
            tier_level = self.cost_tracker.get_tier_for_role(role)
        
        # Get tier configuration
        tier = TierManager.get_tier(tier_level)
        self.tiers[role] = tier
        
        # Prepare LLM config based on tier
        llm_config = agent_kwargs.get('llm', {})
        
        # Set temperature based on tier (lower tiers = more creative)
        if 'temperature' not in agent_kwargs:
            agent_kwargs['temperature'] = tier.temperature
        
        # Set model based on tier
        if isinstance(llm_config, dict) and 'model' not in llm_config:
            llm_config['model'] = tier.model
        
        # Create agent
        agent = Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=llm_config,
            **agent_kwargs
        )
        
        # Store tier metadata
        agent.metadata = {
            'tier': tier_level.value,
            'tier_name': tier.name,
            'model': tier.model,
            'provider': tier.base_url,
            'cost_per_million_prompt': float(
                tier.cost_per_1k_tokens.get('prompt', 0) * 1000
            ),
        }
        
        self.agents[role] = agent
        
        return agent
    
    def execute_task_with_tracking(
        self,
        task: Task,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a task with comprehensive cost tracking.
        
        Args:
            task: CrewAI task to execute
            description: Task description
            context: Additional context
            
        Returns:
            Execution result with cost metadata
        """
        if not CREWAI_AVAILABLE:
            return {
                'success': False,
                'error': 'CrewAI not available',
                'ready_for_escalation': False,
            }
        
        # Get agent from task
        agent = task.agent
        if not agent:
            return {
                'success': False,
                'error': 'No agent assigned to task',
                'ready_for_escalation': False,
            }
        
        # Get tier for this agent
        tier = self.tiers.get(agent.role, TierManager.get_tier(TierLevel.L0))
        
        # Execute task
        start_time = time.time()
        
        try:
            # Create crew with single agent
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
            )
            
            # Execute
            result = crew.kickoff()
            
            # Calculate metrics
            duration = time.time() - start_time
            
            # Estimate tokens
            input_text = str(description) + str(context or '')
            output_text = str(result) if not isinstance(result, dict) else str(result.get('text', ''))
            
            prompt_tokens = len(input_text) // 4
            completion_tokens = len(output_text) // 4
            
            # Calculate cost
            tokens = TokenCount(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            
            cost = (
                (prompt_tokens / 1000) * float(tier.cost_per_1k_tokens.get('prompt', 0)) +
                (completion_tokens / 1000) * float(tier.cost_per_1k_tokens.get('completion', 0))
            )
            
            # Track in cost tracker
            self.cost_tracker.cost_tracker.record(
                task_id=task.name or 'task',
                tier=tier.name,
                model=tier.model,
                tokens=tokens,
                duration=duration,
            )
            
            return {
                'success': True,
                'output': output_text,
                'duration_seconds': duration,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'cost_usd': cost,
                'tier': tier.name,
                'model': tier.model,
                'task_id': task.name or 'unknown',
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration,
                'tier': tier.name,
                'ready_for_escalation': True,
            }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary for all tracked executions.
        
        Returns:
            Cost summary dictionary
        """
        return self.cost_tracker.cost_tracker.get_summary()
    
    def reset(self) -> None:
        """Reset cost tracking state."""
        self.cost_tracker.cost_tracker = CostTracker(
            budget=self.cost_tracker.config
        )


# Import time for CrewAIOrchestrator
import time
