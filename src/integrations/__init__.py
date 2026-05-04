"""Integration support for AI frameworks (CrewAI, LangChain, etc.).

This package provides integration modules for popular AI frameworks:

- crewai_tools: Cost-aware tool decorators for CrewAI
- crewai_integration: Enhanced CrewAI orchestrator with cost tracking
"""

from .crewai_tools import (
    cost_aware_tool,
    create_cost_aware_base_tool,
    wrap_for_crewai,
    CostAwareToolMixin,
)

from .crewai_integration import (
    CrewAIConfig,
    CrewAICostTracker,
    CrewAIOrchestrator,
    DEFAULT_ROLE_TO_TIER_MAPPING,
)

__all__ = [
    # CrewAI tools
    'cost_aware_tool',
    'create_cost_aware_base_tool',
    'wrap_for_crewai',
    'CostAwareToolMixin',
    
    # CrewAI integration
    'CrewAIConfig',
    'CrewAICostTracker',
    'CrewAIOrchestrator',
    'DEFAULT_ROLE_TO_TIER_MAPPING',
]
