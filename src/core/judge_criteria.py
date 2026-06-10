# src/core/judge_criteria.py
CODE_CRITERIA = ["correctness", "completeness", "style", "safety", "production_ready"]
QA_CRITERIA = ["accuracy", "completeness", "clarity", "helpfulness"]
PLAN_CRITERIA = ["atomicity", "coder_fitness", "anti_pattern_coverage", "dependency_correctness", "file_specificity", "coder_task_size"]

# Size limits for PI coder tasks (enforced by plan judge)
MAX_CODER_TASK_KB = 12       # per-task prompt size in KB — raised for multi-pass
MAX_CODER_TASK_FILES = 20    # max files per coder task — raised from 5 for real-world tasks
MAX_CODER_TASK_TESTS = 20    # max test functions per task — raised from 8

def detect_task_type(task: str) -> str:
    """Return 'code', 'plan', or 'qa' based on task content."""
    plan_keywords = ["decompose", "decomposition", "break down", "subtask", "plan", "planning",
                     "task list", "implementation plan", "architecture plan",
                     "design doc", "specification", "blueprint", "roadmap",
                     "mid-tier planner", "planner"]

    code_keywords = ["write code", "implement", "function", "class", "method",
                     "bug", "fix", "refactor", "optimize", "algorithm",
                     "compiles", "runs", "test", "def ", "code", "coding",
                     "build", "create file", "add route", "add endpoint"]

    plan_score = sum(1 for kw in plan_keywords if kw.lower() in task.lower())
    code_score = sum(1 for kw in code_keywords if kw.lower() in task.lower())

    # Plan keywords are stronger signals — fewer matches needed
    if plan_score >= 2:
        return "plan"
    # Code is the default — low bar to clear
    if code_score >= 1:
        return "code"
    return "qa"