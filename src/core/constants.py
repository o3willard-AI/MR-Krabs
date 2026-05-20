"""Constants extracted from across the codebase.

Centralises hardcoded values that were duplicated in multiple files.
"""

# LM Studio (local inference)
LM_STUDIO_HOST = "192.168.101.21"
LM_STUDIO_PORT = 1234
LM_STUDIO_BASE_URL = f"http://{LM_STUDIO_HOST}:{LM_STUDIO_PORT}/v1"

# OpenRouter (cloud API gateway)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://github.com/o3willard-AI/MR-Krabs"

# Orchestrator defaults
DEFAULT_MAX_RETRIES_PER_TIER = 3
DEFAULT_JUDGE_MODEL = "Judge"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_ACCEPTANCE_THRESHOLD = 0.7
JUDGE_MAX_TOKENS = 1024
LLM_MAX_TOKENS = 8192
OUTPUT_TRUNCATION_LIMIT = 8000

# Human gate
HUMAN_GATE_TIMEOUT_MINUTES = 15

# Budget
DEFAULT_DAILY_BUDGET_USD = "10.00"
