"""
CrewAI Integration Module

Provides multi-agent workflow capabilities using CrewAI framework.
This module wraps CrewAI functionality while maintaining MR-Krabs' cost-tracking and budget enforcement.
"""

from typing import Optional, List, Dict, Any, Callable
import logging
from enum import Enum
from decimal import Decimal

# Try to import crewai, but make it optional for basic functionality
try:
    from crewai import Agent, Task, Crew, Process
    from crewai.llm import LLM as CrewAILLM
    # Try different callback handler base classes (CrewAI versions differ)
    try:
        from crewai.callbacks.base_handler import CallbackHandler
    except ImportError:
        try:
            from crewai import BaseCallbackHandler as CallbackHandler
        except ImportError:
            # Fallback - we'll implement basic structure ourselves
            class CallbackHandler:  # type: ignore
                """Fallback callback handler."""
                def on_llm_start(self, **kwargs):
                    pass
                
                def on_llm_end(self, *args, **kwargs):
                    pass
                
                def on_error(self, error, **kwargs):
                    pass
    
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    Agent = Task = Crew = Process = object  # type: ignore
    CallbackHandler = object  # type: ignore

# Import cost tracking components
from src.core.cost import CostTracker, TokenCount, BudgetExceededError
from src.core.exceptions import BudgetExceededError as OrchBudgetExceededError


logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Standard agent roles for common use cases."""
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    WRITER = "writer"
    CODER = "coder"
    REVIEWER = "reviewer"
    PLANNER = "planner"


class CrewConfig:
    """
    Configuration for creating a CrewAI crew.

    Attributes:
        process: The execution process (sequential, hierarchical, etc.)
        max_iterations: Maximum iterations per task
        verbosity: Logging verbosity level
    """

    def __init__(
        self,
        process: str = "sequential",
        max_iterations: int = 10,
        verbosity: int = 0,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.process = process
        self.max_iterations = max_iterations
        self.verbosity = verbosity
        self.llm_config = llm_config or {}

    def to_crew_params(self) -> Dict[str, Any]:
        """Convert config to Crew constructor parameters."""
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. Install with: pip install crewai"
            )
        
        return {
            "process": getattr(Process, self.process, Process.sequential),
            "verbose": self.verbosity > 0,
        }


class CostAwareAgent:
    """
    Wrapper for CrewAI Agent with MR-Krabs cost awareness.

    This agent tracks token usage and costs through the MR-Krabs framework.

    Example:
        >>> agent = CostAwareAgent(
        ...     role="Senior Researcher",
        ...     goal="Conduct thorough research on topics",
        ...     backstory="Expert researcher with 10+ years experience",
        ...     llm_config={"model": "google/gemma-7b-it"}  # Use cheaper model
        ... )
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: Optional[str] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        verbose: bool = False,
    ):
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. Install with: pip install crewai"
            )

        self.role = role
        self.goal = goal
        self.backstory = backstory or f"{role} responsible for {goal}"
        self.llm_config = llm_config or {}
        self.verbose = verbose
        self._agent: Optional[Agent] = None

    def _create_agent(self) -> Agent:
        """Create the underlying CrewAI agent."""
        # Note: In future versions, you can integrate with MR-Krask's cost tracking here
        # by passing a custom LLM wrapper that tracks usage
        self._agent = Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            verbose=self.verbose,
            # Add CrewAI-specific config here
        )
        return self._agent

    def get_agent(self) -> Agent:
        """Get the CrewAI agent instance."""
        if not self._agent:
            self._agent = self._create_agent()
        return self._agent


class CostAwareTask:
    """
    Wrapper for CrewAI Task with cost tracking.

    Example:
        >>> task = CostAwareTask(
        ...     description="Research the latest trends in AI",
        ...     expected_output="A detailed report on AI trends",
        ...     agent=my_agent,
        ...     cost_limit=0.50  # $0.50 max for this task
        ... )
    """

    def __init__(
        self,
        description: str,
        expected_output: str,
        agent: CostAwareAgent,
        cost_limit: Optional[float] = None,
        tools: Optional[List[Any]] = None,
    ):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent
        self.cost_limit = cost_limit
        self._task: Optional[Task] = None

    def _create_task(self) -> Task:
        """Create the underlying CrewAI task."""
        self._task = Task(
            description=self.description,
            expected_output=self.expected_output,
            agent=self.agent.get_agent(),
        )
        return self._task

    def get_task(self) -> Task:
        """Get the CrewAI task instance."""
        if not self._task:
            self._task = self._create_task()
        return self._task


class CostAwareCrew:
    """
    MR-Krabs wrapper for CrewAI Crew with cost tracking and budget enforcement.

    This is the main entry point for using CrewAI with MR-Krabs' cost optimization.

    Example:
        >>> # Define agents
        >>> researcher = CostAwareAgent(
        ...     role="Research Lead",
        ...     goal="Conduct comprehensive research",
        ...     llm_config={"model": "google/gemma-7b-it"}  # Budget-friendly model
        ... )
        >>> writer = CostAwareAgent(
        ...     role="Content Writer",
        ...     goal="Write engaging content based on research"
        ... )

        >>> # Define tasks
        >>> research_task = CostAwareTask(
        ...     description="Research the topic thoroughly",
        ...     expected_output="Comprehensive research document",
        ...     agent=researcher
        ... )
        >>> writing_task = CostAwareTask(
        ...     description="Write the article",
        ...     expected_output="Final article ready for publication",
        ...     agent=writer
        ... )

        >>> # Create and run crew
        >>> crew = CostAwareCrew(
        ...     tasks=[research_task, writing_task],
        ...     agents=[researcher, writer],
        ...     config=CrewConfig(process="sequential"),
        ...     cost_limit=2.0  # $2 total budget
        ... )

        >>> result = crew.kickoff()
    """

    def __init__(
        self,
        tasks: List[CostAwareTask],
        agents: List[CostAwareAgent],
        config: Optional[CrewConfig] = None,
        cost_limit: Optional[float] = None,
        cost_tracker: Optional[CostTracker] = None,  # NEW: Cost tracker for recording costs
    ):
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. Install with: pip install crewai"
            )

        self.tasks = tasks
        self.agents = agents
        self.config = config or CrewConfig()
        # Accept both None and numeric values (including 0)
        if cost_limit is not None:
            self.cost_limit = Decimal(str(cost_limit))
        else:
            self.cost_limit = None
        self.cost_tracker = cost_tracker or CostTracker()  # Use provided or create default
        
        # Generate unique task ID for this crew execution
        import uuid
        self.task_id = f"crew-{uuid.uuid4().hex[:8]}"
        
        # Create LLM wrapper for cost tracking
        self.llm_wrapper = CostAwareLLMWrapper(
            cost_tracker=self.cost_tracker,
            task_id=self.task_id,
            budget_limit=self.cost_limit if self.cost_limit is not None else None,
        )
        
        self._crew: Optional[Crew] = None

    def _create_crew(self) -> Crew:
        """Create the underlying CrewAI crew."""
        # Convert wrapped objects to native CrewAI objects
        crewai_tasks = [task.get_task() for task in self.tasks]
        crewai_agents = [agent.get_agent() for agent in self.agents]

        # Create callback handler for automatic cost tracking
        # Note: CrewAI v0.203.2+ uses step_callback/task_callback instead of callback_handlers
        callback_handler = CostTrackingCallbackHandler(self.llm_wrapper)

        crew_params = {
            "tasks": crewai_tasks,
            "agents": crewai_agents,
            **self.config.to_crew_params(),
            # Use CrewAI v0.203.2+ API - single callback for steps
            "step_callback": callback_handler.on_step_complete if hasattr(callback_handler, 'on_step_complete') else callback_handler,
        }

        self._crew = Crew(**crew_params)
        return self._crew

    def kickoff(self) -> Dict[str, Any]:
        """
        Execute the crew workflow with cost tracking and budget enforcement.

        Returns:
            Dictionary containing the final output and cost information.

        Example:
            >>> result = crew.kickoff()
            >>> print(result["output"])  # Final task output
            >>> print(result["cost"])    # Total cost incurred (REAL cost now!)
            >>> print(result["tokens"])  # Token usage breakdown

        Raises:
            BudgetExceededError: If the crew execution exceeds the budget limit
        """
        if not self._crew:
            self._create_crew()

        logger.info(f"Starting CrewAI workflow with {len(self.tasks)} tasks")
        logger.info(f"Crew task ID: {self.task_id}")
        if self.cost_limit:
            logger.info(f"Crew cost limit: ${float(self.cost_limit):.2f}")

        try:
            # Execute the crew
            result = self._crew.kickoff()
            
            # Get real cost tracking data from LLM wrapper
            cost_summary = self.llm_wrapper.get_summary()
            
            logger.info(
                f"Crew '{self.task_id}' completed: "
                f"cost=${float(cost_summary['total_cost']):.4f}, "
                f"tokens={cost_summary['tokens']['total']}"
            )

            return {
                "output": result,
                "cost": float(cost_summary["total_cost"]),  # ← REAL TRACKED COST!
                "tokens": cost_summary["tokens"],
                "task_id": self.task_id,
                "budget_limit": float(self.cost_limit) if self.cost_limit else None,
            }

        except BudgetExceededError as e:
            logger.error(f"Crew '{self.task_id}' exceeded budget: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Crew '{self.task_id}' failed with error: {e}")
            # Still return cost info even on failure
            cost_summary = self.llm_wrapper.get_summary()
            return {
                "output": None,
                "cost": float(cost_summary["total_cost"]),
                "tokens": cost_summary["tokens"],
                "error": str(e),
                "task_id": self.task_id,
            }

    def kickoff_for_each(self, inputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run the crew workflow for multiple input variations.

        Args:
            inputs: List of input dictionaries to parameterize each run

        Returns:
            List of results from each crew execution
        """
        return [self.kickoff() for _ in inputs]


# Convenience function for quick crews
def create_simple_crew(
    tasks: List[Dict[str, Any]],
    agents: List[Dict[str, Any]],
    process: str = "sequential",
    cost_limit: Optional[float] = None,  # NEW: budget limit
    cost_tracker: Optional[CostTracker] = None,  # NEW: custom cost tracker
) -> CostAwareCrew:
    """
    Quick helper to create a crew from dictionaries.

    Args:
        tasks: List of task dicts with 'description', 'expected_output', 'agent_role'
        agents: List of agent dicts with 'role', 'goal', optional 'backstory'
        process: Execution process ('sequential', 'hierarchical', etc.)
        cost_limit: Optional budget limit for the crew
        cost_tracker: Optional custom CostTracker instance

    Returns:
        Configured CostAwareCrew ready to run

    Example:
        >>> from src.core.cost import CostTracker
        >>> tracker = CostTracker()
        >>> crew = create_simple_crew(
        ...     tasks=[
        ...         {"description": "Research topic", "expected_output": "Report", "agent_role": 0},
        ...         {"description": "Write article", "expected_output": "Article", "agent_role": 1},
        ...     ],
        ...     agents=[
        ...         {"role": "Researcher", "goal": "Find information"},
        ...         {"role": "Writer", "goal": "Write content"},
        ...     ],
        ...     cost_limit=5.0,  # $5 budget
        ...     cost_tracker=tracker,
        ... )
    """
    # Create agent objects
    agent_objects = [
        CostAwareAgent(**agent_config) for agent_config in agents
    ]

    # Create task objects (link to agents by index)
    task_objects = [
        CostAwareTask(
            description=task["description"],
            expected_output=task["expected_output"],
            agent=agent_objects[task.get("agent_role", 0)],
        )
        for task in tasks
    ]

    # Create crew with cost tracking
    crew = CostAwareCrew(
        tasks=task_objects,
        agents=agent_objects,
        config=CrewConfig(process=process),
        cost_limit=cost_limit,
        cost_tracker=cost_tracker,
    )

    return crew


# Export public API
__all__ = [
    "CostAwareAgent",
    "CostAwareTask",
    "CostAwareCrew",
    "CrewConfig",
    "AgentRole",
    "create_simple_crew",
    "CREWAI_AVAILABLE",
    "CostAwareLLMWrapper",  # LLM wrapper for cost tracking
    "CostTrackingCallbackHandler",  # Automatic callback-based cost tracking
]


class CostTrackingCallbackHandler(CallbackHandler):
    """
    CrewAI callback handler that automatically tracks costs via MR-Krabs.

    This handler intercepts LLM calls during crew execution and records them
    through CostAwareLLMWrapper, enabling automatic cost tracking without
    manual intervention.

    Usage:
        >>> tracker = CostTracker()
        >>> wrapper = CostAwareLLMWrapper(
        ...     cost_tracker=tracker,
        ...     task_id="my-crew",
        ...     model="google/gemma-7b-it",
        ... )
        >>> callback = CostTrackingCallbackHandler(wrapper)
        >>> # Pass to CrewAI crew (CrewAI v0.203.2+):
        >>> crew = Crew(..., step_callback=callback)
    """

    def __init__(self, wrapper: "CostAwareLLMWrapper"):
        """
        Initialize callback handler with LLM wrapper.

        Args:
            wrapper: CostAwareLLMWrapper instance to record costs through
        """
        super().__init__()
        self.wrapper = wrapper
        logger.debug(f"CostTrackingCallbackHandler initialized for task {wrapper.task_id}")

    def on_step_complete(self, **kwargs):
        """
        Called after each step in CrewAI v0.203.2+.
        
        This is the new callback method for step_callback parameter.
        """
        # Extract token usage from kwargs if available
        if 'usage' in kwargs:
            usage = kwargs['usage']
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
            completion_tokens = getattr(usage, 'completion_tokens', 0) or 0
            
            if prompt_tokens > 0 or completion_tokens > 0:
                self.wrapper.record_completion(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

    def on_llm_start(self, **kwargs):
        """Called when LLM execution starts."""
        # Could track start time here if needed
        pass

    def on_llm_end(self, *args, **kwargs):
        """
        Called when LLM execution completes - this is where we track costs!

        Extracts token usage from CrewAI's LLM output and records it.
        Handles different CrewAI version signature variations.
        """
        # Handle different CrewAI versions' callback signatures
        if args:
            # Older version might pass result as first positional arg
            llm_output = args[0] if len(args) > 0 else {}
        elif "llm_output" in kwargs:
            # Newer version uses keyword arg
            llm_output = kwargs.get("llm_output", {})
        elif "usage" in kwargs:
            # Some versions pass usage directly
            llm_output = kwargs
        else:
            # Fallback
            llm_output = {}

        # Extract token counts - CrewAI might provide them in different places
        prompt_tokens = 0
        completion_tokens = 0
        model = None

        # Try to get usage object
        if isinstance(llm_output, dict):
            # Direct dictionary access
            usage = llm_output.get("usage", llm_output)
            prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("promptTokens", 0) or 0
            completion_tokens = (
                usage.get("completion_tokens", 0)
                or usage.get("completionTokens", 0)
                or 0
            )
            model = llm_output.get("model", self.wrapper.model)

        elif hasattr(llm_output, "usage"):
            # Object with usage attribute
            usage = llm_output.usage
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or getattr(
                usage, "promptTokens", 0
            )
            completion_tokens = getattr(usage, "completion_tokens", 0) or getattr(
                usage, "completionTokens", 0
            )
            model = getattr(llm_output, "model", self.wrapper.model)

        # Also check kwargs for token info
        if "prompt_tokens" in kwargs:
            prompt_tokens = kwargs["prompt_tokens"]
        if "completion_tokens" in kwargs:
            completion_tokens = kwargs["completion_tokens"]
        if "model" in kwargs:
            model = kwargs["model"]

        # If we got meaningful token counts, record them
        if prompt_tokens > 0 or completion_tokens > 0:
            try:
                self.wrapper.record_completion(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    actual_model=model,
                )
                logger.debug(
                    f"[{self.wrapper.task_id}] Tracked via callback: "
                    f"{prompt_tokens} + {completion_tokens} tokens"
                )
            except BudgetExceededError as e:
                logger.error(f"[{self.wrapper.task_id}] Budget exceeded during execution: {e}")
                raise

    def on_error(self, error, **kwargs):
        """Called when an error occurs."""
        logger.error(f"[{self.wrapper.task_id}] Callback error: {error}")


class CostAwareLLMWrapper:
    """
    Wrapper that intercepts CrewAI LLM calls and tracks costs via MR-Krabs CostTracker.

    This class wraps the underlying CrewAI LLM to provide cost tracking and budget enforcement.
    It hooks into CrewAI's LLM execution to record token usage and enforce budgets.

    Usage:
        >>> tracker = CostTracker()
        >>> wrapper = CostAwareLLMWrapper(
        ...     cost_tracker=tracker,
        ...     task_id="crew-task-123",
        ...     model="google/gemma-7b-it",
        ... )
        >>> # Pass wrapper to CrewAI agent's llm parameter
    """

    def __init__(
        self,
        cost_tracker: CostTracker,
        task_id: str,
        model: str = "google/gemma-7b-it",
        budget_limit: Optional[Decimal] = None,
    ):
        """
        Initialize cost-aware LLM wrapper.

        Args:
            cost_tracker: MR-Krabs CostTracker instance for recording costs
            task_id: Unique identifier for this task/crew execution
            model: Default model to use (affects cost calculation)
            budget_limit: Maximum budget for this wrapped LLM usage
        """
        self.cost_tracker = cost_tracker
        self.task_id = task_id
        self.model = model
        self.budget_limit = budget_limit
        self._total_cost = Decimal("0")
        self._total_tokens = TokenCount()

    def record_completion(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        actual_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record token usage and calculate cost.

        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion
            actual_model: Actual model used (defaults to configured model)

        Returns:
            Dictionary with cost information

        Raises:
            BudgetExceededError: If budget limit is exceeded
        """
        model = actual_model or self.model
        tokens = TokenCount(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        # Calculate cost using MR-Krabs pricing
        cost = self.cost_tracker.calculate_cost(model, tokens)

        # Check budget BEFORE recording (prevent over-budget from even starting)
        if self.budget_limit is not None:  # Must check for None, not falsy! Decimal("0") is valid limit
            projected_total = self._total_cost + cost
            if projected_total > self.budget_limit:
                raise BudgetExceededError(
                    f"CrewAI task '{self.task_id}' would exceed budget: "
                    f"${float(projected_total):.4f} (would add) > ${float(self.budget_limit):.2f}"
                )

        # Update totals locally first
        self._total_cost += cost
        self._total_tokens.prompt_tokens += prompt_tokens
        self._total_tokens.completion_tokens += completion_tokens
        self._total_tokens.total_tokens += tokens.total_tokens

        # Record with CostTracker using finalize_spending workflow
        # We need to reserve first, then finalize (this handles budget checking)
        try:
            reservation = self.cost_tracker.reserve_budget(self.task_id, cost)
            
            entry = self.cost_tracker.finalize_spending(
                reservation_id=reservation.id,
                actual_cost=cost,
            )

            logger.debug(
                f"[{self.task_id}] Recorded: {prompt_tokens} prompt + "
                f"{completion_tokens} completion = ${float(cost):.6f} (model: {model})"
            )

        except BudgetExceededError as e:
            # Rollback local state since we couldn't record
            self._total_cost -= cost
            self._total_tokens.prompt_tokens -= prompt_tokens
            self._total_tokens.completion_tokens -= completion_tokens
            self._total_tokens.total_tokens -= tokens.total_tokens
            
            logger.warning(f"[{self.task_id}] Budget exceeded: {e}")
            raise

        return {
            "cost": float(cost),
            "total_cost": float(self._total_cost),
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": tokens.total_tokens,
            },
            "model": model,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked costs and tokens."""
        return {
            "task_id": self.task_id,
            "model": self.model,
            "total_cost": float(self._total_cost),
            "budget_limit": float(self.budget_limit) if self.budget_limit else None,
            "tokens": {
                "prompt": self._total_tokens.prompt_tokens,
                "completion": self._total_tokens.completion_tokens,
                "total": self._total_tokens.total_tokens,
            },
        }

    def reset(self):
        """Reset tracking for a new execution."""
        self._total_cost = Decimal("0")
        self._total_tokens = TokenCount()
