#!/usr/bin/env python3
"""CrewAI integration for cost-optimized orchestration."""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import logging

try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    logging.warning("CrewAI not available - running in simulation mode")

from skills.cost_optimized_orchestration.orchestrator import (
    CostOptimizedOrchestrator, TierConfig, ExecutionResult
)

logger = logging.getLogger(__name__)


@dataclass
class CrewAITierMapping:
    """Mapping between tier names and CrewAI agent configurations."""
    tier: str
    role: str
    goal: str
    backstory: str
    llm_config: Dict[str, Any]
    allow_delegation: bool = True
    verbose: bool = True


class CrewAIOrchestrator:
    """Integrates CrewAI with cost-optimized tiered orchestration."""
    
    def __init__(
        self,
        base_orchestrator: CostOptimizedOrchestrator,
        crewai_tier_mappings: Optional[Dict[str, CrewAITierMapping]] = None
    ):
        """
        Initialize CrewAI orchestrator.
        
        Args:
            base_orchestrator: CostOptimizedOrchestrator instance
            crewai_tier_mappings: Custom mappings from tiers to CrewAI configs
        """
        self.base_orchestrator = base_orchestrator
        self.tier_mappings = crewai_tier_mappings or self._create_default_mappings()
        
        if not CREWAI_AVAILABLE:
            logger.warning("CrewAI not installed - using simulation mode")
        
        self.agents: Dict[str, Optional[Agent]] = {}
        self._initialize_agents()
    
    def _create_default_mappings(self) -> Dict[str, CrewAITierMapping]:
        """Create default mappings from tiers to CrewAI configurations."""
        return {
            "L0-Planner": CrewAITierMapping(
                tier="L0-Planner",
                role="Technical Planner",
                goal="Analyze requirements and create detailed implementation plans",
                backstory="Expert at breaking down complex problems into manageable tasks. "
                         "Focuses on practical, implementable solutions.",
                llm_config={
                    "model": "gpt-4-turbo",  # Would map to actual tier model
                    "temperature": 0.3
                }
            ),
            "L0-Coder": CrewAITierMapping(
                tier="L0-Coder",
                role="Junior Developer",
                goal="Write clean, working code based on specifications",
                backstory="Enthusiastic coder who follows instructions precisely. "
                         "Prefers simple, straightforward solutions.",
                llm_config={
                    "model": "gpt-4-turbo",
                    "temperature": 0.7
                }
            ),
            "L0-Reviewer": CrewAITierMapping(
                tier="L0-Reviewer",
                role="Code Reviewer",
                goal="Review code for bugs, best practices, and compliance with requirements",
                backstory="Detail-oriented engineer with sharp eye for code quality. "
                         "Catches issues before they become problems.",
                llm_config={
                    "model": "gpt-4-turbo",
                    "temperature": 0.3
                }
            ),
            "L1-Coder": CrewAITierMapping(
                tier="L1-Coder",
                role="Senior Developer",
                goal="Solve complex coding problems and fix difficult bugs",
                backstory="Experienced developer who handles challenging implementations "
                         "and architectural decisions.",
                llm_config={
                    "model": "gpt-4-turbo",
                    "temperature": 0.7
                }
            ),
            "L3-Architect": CrewAITierMapping(
                tier="L3-Architect",
                role="System Architect",
                goal="Design system architecture and make high-level technical decisions",
                backstory="Seasoned architect with deep expertise in system design "
                         "and scalability considerations.",
                llm_config={
                    "model": "gpt-4-turbo",
                    "temperature": 0.3
                }
            )
        }
    
    def _initialize_agents(self):
        """Initialize CrewAI agents for each tier."""
        if not CREWAI_AVAILABLE:
            self.agents = {tier: None for tier in self.tier_mappings}
            return
        
        for tier, mapping in self.tier_mappings.items():
            # Get tier config from base orchestrator
            tier_config = self.base_orchestrator.tiers.get(tier)
            
            # Create agent
            agent = Agent(
                role=mapping.role,
                goal=mapping.goal,
                backstory=mapping.backstory,
                llm=mapping.llm_config,
                allow_delegation=mapping.allow_delegation,
                verbose=mapping.verbose
            )
            
            # Store metadata about tier
            agent.metadata = {
                "tier": tier,
                "original_model": tier_config.model if tier_config else "unknown",
                "provider": tier_config.provider if tier_config else "unknown",
                "estimated_cost_per_million": tier_config.cost_per_million_prompt if tier_config else 0.0
            }
            
            self.agents[tier] = agent
            
        logger.info(f"Initialized {len(self.agents)} CrewAI agents")
    
    def _create_crewai_task(self, tier: str, description: str, context: Dict[str, Any]) -> Task:
        """Create a CrewAI task from tier and description."""
        if tier not in self.agents or self.agents[tier] is None:
            raise ValueError(f"No agent available for tier: {tier}")
        
        mapping = self.tier_mappings[tier]
        
        # Format context for task description
        context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
        
        task = Task(
            description=f"{description}\n\nContext:\n{context_str}",
            agent=self.agents[tier],
            expected_output="Complete implementation or analysis as specified",
            async_execution=False
        )
        
        return task
    
    def execute_with_crewai(self, tier: str, description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task using CrewAI agents.
        
        Args:
            tier: Which tier/agent to use
            description: Task description
            context: Additional context
            
        Returns:
            Result dictionary compatible with base orchestrator
        """
        if not CREWAI_AVAILABLE:
            logger.warning("CrewAI not available - falling back to base orchestrator")
            # Use base orchestrator's LLM caller
            tier_config = self.base_orchestrator.tiers.get(tier)
            if not tier_config:
                return {
                    "success": False,
                    "error": f"Unknown tier: {tier}",
                    "ready_for_escalation": True
                }
            
            system_prompt = f"You are a {tier} assistant. {description}"
            user_prompt = f"Task: {description}\n\nContext:\n{context}"
            
            return self.base_orchestrator._call_llm_with_retry(
                tier=tier,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=tier_config.temperature
            )
        
        # Create and execute CrewAI task
        try:
            task = self._create_crewai_task(tier, description, context)
            
            # Create a simple crew with just this agent
            crew = Crew(
                agents=[self.agents[tier]],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            
            # Execute
            result = crew.kickoff()
            
            # Estimate token usage (simplified)
            # In real implementation, would get from LLM provider
            prompt_tokens = len(str(description) + str(context)) // 4
            completion_tokens = len(str(result)) // 4
            
            # Get tier config for cost calculation
            tier_config = self.base_orchestrator.tiers.get(tier)
            cost = 0.0
            if tier_config:
                cost = tier_config.estimate_cost(prompt_tokens, completion_tokens)
            
            return {
                "success": True,
                "output": str(result),
                "attempt": 1,
                "duration_seconds": 0.0,  # Would measure actual time
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": cost,
                "context_simplified": False,
                "crewai_result": True
            }
            
        except Exception as e:
            logger.error(f"CrewAI execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "attempts": 1,
                "ready_for_escalation": True
            }
    
    def execute_task_with_escalation(
        self,
        task_id: str,
        description: str,
        context: Dict[str, Any],
        initial_tier: str = "L0-Coder"
    ) -> ExecutionResult:
        """
        Execute task with tiered escalation using CrewAI agents.
        
        This combines the cost optimization logic with CrewAI execution.
        """
        logger.info(f"Executing task {task_id} with CrewAI escalation")
        
        # Override base orchestrator's LLM caller with CrewAI executor
        original_llm_caller = self.base_orchestrator.llm_caller
        
        def crewai_llm_caller(tier, system_prompt, user_prompt, temperature):
            # Convert to CrewAI format
            crewai_description = f"{system_prompt}\n\n{user_prompt}"
            crewai_context = {"temperature": temperature}
            
            result = self.execute_with_crewai(tier, crewai_description, crewai_context)
            
            if result.get("success"):
                return result["output"]
            else:
                raise Exception(result.get("error", "CrewAI execution failed"))
        
        try:
            # Temporarily replace LLM caller
            self.base_orchestrator.llm_caller = crewai_llm_caller
            
            # Execute using base orchestrator's escalation logic
            result = self.base_orchestrator.execute_task(
                task_id=task_id,
                description=description,
                context=context,
                initial_tier=initial_tier
            )
            
            return result
            
        finally:
            # Restore original LLM caller
            self.base_orchestrator.llm_caller = original_llm_caller


# Example usage
def main():
    """Example of using CrewAIOrchestrator."""
    import json
    
    # Create base orchestrator
    base_orchestrator = CostOptimizedOrchestrator(budget_daily_usd=10.0)
    
    # Create CrewAI integration
    crewai_orchestrator = CrewAIOrchestrator(base_orchestrator)
    
    # Example task
    task_id = "crewai_example_1"
    description = "Create a Python function that calculates Fibonacci numbers"
    context = {
        "requirements": "Function should take n as input and return nth Fibonacci number",
        "constraints": "Use iterative approach for efficiency",
        "testing": "Include test cases for n=0, n=1, n=10"
    }
    
    print("=" * 60)
    print("CrewAI Cost-Optimized Orchestration Demo")
    print("=" * 60)
    
    # Execute single tier with CrewAI
    print(f"\n1. Executing with L0-Coder tier...")
    single_result = crewai_orchestrator.execute_with_crewai(
        tier="L0-Coder",
        description=description,
        context=context
    )
    
    print(f"Success: {single_result.get('success')}")
    if single_result.get('success'):
        print(f"Output preview: {single_result.get('output', '')[:200]}...")
        print(f"Estimated cost: ${single_result.get('cost_usd', 0):.6f}")
    else:
        print(f"Error: {single_result.get('error')}")
    
    # Execute with full escalation
    print(f"\n2. Executing with full tier escalation...")
    escalation_result = crewai_orchestrator.execute_task_with_escalation(
        task_id=task_id,
        description=description,
        context=context,
        initial_tier="L0-Coder"
    )
    
    print(f"Final tier: {escalation_result.tier}")
    print(f"Success: {escalation_result.success}")
    print(f"Attempts: {escalation_result.attempts}")
    print(f"Cost: ${escalation_result.cost_usd:.6f}")
    
    # Get summary
    summary = base_orchestrator.get_summary()
    print(f"\n3. Summary:")
    print(f"Total cost: ${summary['total_cost_usd']:.6f}")
    print(f"Success rate: {summary['success_rate']:.1%}")
    
    print("\n" + "=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())