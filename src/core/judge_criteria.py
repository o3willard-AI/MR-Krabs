# src/core/judge_criteria.py
CODE_CRITERIA = ["correctness", "completeness", "style", "safety", "production_ready"]
QA_CRITERIA = ["accuracy", "completeness", "clarity", "helpfulness"]

def detect_task_type(task: str) -> str:
    """Return 'code' or 'qa' based on task content."""
    code_keywords = ["write code", "implement", "function", "class", "method", "bug", "fix", 
                     "refactor", "optimize", "algorithm", "compiles", "runs", "test"]
    
    # First check for exact phrases
    score = sum(1 for kw in code_keywords if kw.lower() in task.lower())
    
    # If we don't have enough matches, look for partial matches in longer words
    if score < 2:
        # Check individual words from the task
        task_words = task.lower().split()
        for word in task_words:
            if any(code_word in word for code_word in ["function", "class", "method", "bug", "fix", "refactor", "algorithm"]):
                score += 1
    
    return "code" if score >= 2 else "qa"