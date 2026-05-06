"""
Example: Using CrewAI with MR-Krabs Cost-Optimized Orchestrator

This demonstrates the multi-agent workflow capabilities using CrewAI,
with automatic cost tracking and budget enforcement.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.crewai_integration import (
    CostAwareAgent,
    CostAwareTask,
    CostAwareCrew,
    CrewConfig,
    create_simple_crew,
    CREWAI_AVAILABLE,
)


def check_requirements():
    """Verify CrewAI is installed."""
    if not CREWAI_AVAILABLE:
        print("❌ CrewAI not installed!")
        print("   Install with: pip install crewai")
        return False
    print("✅ CrewAI is ready!")
    return True


def example_1_simple_crew():
    """Example 1: Create a simple research crew."""
    print("\n" + "=" * 60)
    print("Example 1: Simple Research & Write Workflow")
    print("=" * 60)

    # Define our agents and tasks using the convenience function
    crew = create_simple_crew(
        tasks=[
            {
                "description": (
                    "Research the latest trends in AI cost optimization. "
                    "Focus on multi-tier LLM strategies and budget tracking."
                ),
                "expected_output": "A comprehensive research report with key findings",
                "agent_role": 0,  # Use first agent
            },
            {
                "description": (
                    "Write a blog article based on the research about AI cost optimization."
                ),
                "expected_output": "A well-written blog post ready for publication",
                "agent_role": 1,  # Use second agent
            },
        ],
        agents=[
            {
                "role": "Senior Researcher",
                "goal": "Conduct thorough research on AI and LLM topics",
                "backstory": (
                    "You are an expert researcher with deep knowledge of "
                    "AI systems, LLMs, and cost optimization strategies."
                ),
            },
            {
                "role": "Technical Writer",
                "goal": "Write clear, engaging technical content",
                "backstory": (
                    "You are a skilled technical writer who can translate "
                    "complex concepts into accessible articles."
                ),
            },
        ],
        process="sequential",
    )

    # Run the crew
    result = crew.kickoff()
    print(f"\n📝 Output preview: {str(result['output'])[:500]}...")


def example_2_explicit_agents():
    """Example 2: Explicit agent and task configuration."""
    print("\n" + "=" * 60)
    print("Example 2: Explicit Agent Configuration with Cost Limits")
    print("=" * 60)

    # Define agents with explicit control
    researcher = CostAwareAgent(
        role="Data Analyst",
        goal="Analyze financial data and identify trends",
        backstory="Expert financial analyst with 15 years of experience",
        verbose=True,
    )

    writer = CostAwareAgent(
        role="Report Writer",
        goal="Create detailed financial reports",
        backstory="Skilled business writer specializing in financial reports",
        verbose=True,
    )

    # Define tasks with cost limits
    analysis_task = CostAwareTask(
        description="Analyze the Q4 financial data and identify key trends",
        expected_output="Analysis document with insights and recommendations",
        agent=researcher,
        cost_limit=0.50,  # $0.50 max for this task
    )

    report_task = CostAwareTask(
        description="Write a comprehensive financial report based on the analysis",
        expected_output="Professional financial report ready for stakeholders",
        agent=writer,
        cost_limit=0.75,  # $0.75 max for this task
    )

    # Create crew with total budget
    crew = CostAwareCrew(
        tasks=[analysis_task, report_task],
        agents=[researcher, writer],
        config=CrewConfig(process="sequential", verbosity=1),
        cost_limit=1.25,  # $1.25 total budget ($0.25 buffer)
    )

    # Execute
    result = crew.kickoff()
    print(f"\n📊 Report generated (cost tracking will be added in future)")


def example_3_hierarchical_process():
    """Example 3: Hierarchical process with manager agent."""
    print("\n" + "=" * 60)
    print("Example 3: Hierarchical Process (Manager + Workers)")
    print("=" * 60)

    # In hierarchical mode, CrewAI appoints a manager to coordinate
    crew = create_simple_crew(
        tasks=[
            {
                "description": "Gather requirements for the new feature",
                "expected_output": "Requirements document",
                "agent_role": 0,
            },
            {
                "description": "Design the technical architecture",
                "expected_output": "Architecture specification",
                "agent_role": 1,
            },
            {
                "description": "Implement the feature code",
                "expected_output": "Working code implementation",
                "agent_role": 2,
            },
            {
                "description": "Review and test the implementation",
                "expected_output": "Test results and quality report",
                "agent_role": 3,
            },
        ],
        agents=[
            {"role": "Product Manager", "goal": "Define product requirements"},
            {"role": "System Architect", "goal": "Design system architecture"},
            {"role": "Software Developer", "goal": "Write clean, efficient code"},
            {"role": "QA Engineer", "goal": "Ensure code quality through testing"},
        ],
        process="hierarchical",  # Manager coordinates the work!
    )

    result = crew.kickoff()
    print(f"\n🏗️ Feature development complete!")


def example_4_sequential_chain():
    """Example 4: Sequential task chain (most common pattern)."""
    print("\n" + "=" * 60)
    print("Example 4: Sequential Task Chain")
    print("=" * 60)

    # Sequential is best for linear workflows where each task depends on the previous
    crew = CostAwareCrew(
        tasks=[
            CostAwareTask(
                description="Research the customer feedback data",
                expected_output="Summary of customer sentiment and key themes",
                agent=CostAwareAgent(
                    role="Data Researcher",
                    goal="Analyze customer feedback",
                ),
            ),
            CostAwareTask(
                description="Draft email responses based on the research",
                expected_output="Email templates for common feedback types",
                agent=CostAwareAgent(
                    role="Customer Success Writer",
                    goal="Write empathetic customer communications",
                ),
            ),
        ],
        agents=[
            CostAwareAgent(role="Data Researcher", goal="Analyze feedback"),
            CostAwareAgent(role="Customer Success Writer", goal="Write emails"),
        ],
        config=CrewConfig(process="sequential"),
    )

    result = crew.kickoff()


if __name__ == "__main__":
    print("=" * 60)
    print("MR-Krabs CrewAI Integration Examples")
    print("=" * 60)

    if not check_requirements():
        sys.exit(1)

    # Uncomment to run examples (requires API keys configured):
    # example_1_simple_crew()
    # example_2_explicit_agents()
    # example_3_hierarchical_process()
    # example_4_sequential_chain()

    print("\n" + "=" * 60)
    print("Examples ready!")
    print("=" * 60)
    print("\nTo run individual examples, uncomment the function calls in:")
    print(f"  {Path(__file__).resolve()}")
    print("\nDon't forget to set your API keys:")
    print("  export OPENROUTER_API_KEY=your_key_here")
    print("  # Or configure in .cost_orchestrator.toml")
