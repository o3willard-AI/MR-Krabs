#!/usr/bin/env python3
"""Judge - LLM-powered quality evaluator for code/text output.

Best Practice: The Judge model should ALWAYS be a reasoning-specialized LLM.
See model_config.py docstring for rationale. The Judge is the quality gate
for the entire escalation pipeline — its reliability is the ceiling on the
system's ability to distinguish good code from bad.

By default, MR-Krabs uses a dedicated "Judge" model entry (not an agent tier),
currently anthropic/claude-sonnet-4.6, to keep the quality gate independent
from the worker agents.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from src.core.constants import JUDGE_MAX_TOKENS, OPENROUTER_REFERER
from src.core.model_config import get_models
from src.core.judge_criteria import CODE_CRITERIA, QA_CRITERIA, PLAN_CRITERIA, detect_task_type
from src.core.model_profiles import get_known_failures, KnownFailure


@dataclass
class Verdict:
    """Represents the verdict from a judge evaluation."""
    
    accepted: bool
    score: float          # 0.0 - 1.0
    critique: str         # specific, actionable feedback with coaching  
    checks_passed: List[str]
    checks_failed: List[str]


class Judge:
    """LLM-powered quality evaluator for code/text output.
    
    The Judge evaluates agent outputs and produces Verdicts with
    scored critiques. When output is rejected, the critique is fed
    back to the agent as coaching for the next retry attempt.
    """
    
    def __init__(self, model: str = "Judge", criteria: Optional[List[str]] = None, 
                 acceptance_threshold: float = 0.7):
        """Initialize the Judge with specified model and criteria.
        
        Args:
            model: The LLM model to use for judging (default: "L2-Coder")
            criteria: Custom evaluation criteria (default: auto-detected based on task)
            acceptance_threshold: Minimum score to accept output (default: 0.7)
        """
        self.model = model
        self.criteria = criteria or ["correctness", "completeness", "style", "safety"]
        self.acceptance_threshold = acceptance_threshold
        
        # Get the judge model configuration
        self.model_config = get_models().get(model)
        if not self.model_config:
            raise ValueError(f"Unknown judge model: {model}")
        
        # Use low temperature for consistent evaluations
        self.temperature = 0.1
        
        # Initialize prompt template
        self._prompt_template = None
    
    @property
    def prompt_template(self) -> str:
        """Get the current prompt template."""
        return self._prompt_template
    
    @prompt_template.setter
    def prompt_template(self, value: str) -> None:
        """Set a custom prompt template."""
        self._prompt_template = value
    
    def evaluate(self, task: str, output: str, model_profile_key: Optional[str] = None) -> Verdict:
        """Evaluate code/text output against the specified task.
        
        Args:
            task: The original task description
            output: The output to evaluate
            model_profile_key: Optional model profile key for known-failure injection
        """
        # Truncate output if it's too long (8000 chars max before sending to judge)
        if len(output) > 8000:
            output = output[:8000] + "\n[Output truncated due to length limit]"
        
        # Determine task type for criteria selection
        if self.criteria is None:
            task_type = detect_task_type(task)
            if task_type == "plan":
                criteria = PLAN_CRITERIA
            elif task_type == "code":
                criteria = CODE_CRITERIA
            else:
                criteria = QA_CRITERIA
        else:
            criteria = self.criteria
        
        # Prepare the prompt for the judge LLM
        if self._prompt_template is not None:
            prompt_template = self._prompt_template
        else:
            prompt_template = '''You are an impartial code quality judge. Your job is to evaluate 
whether an AI assistant's output correctly solves the given task and — if it 
does not — provide specific, actionable coaching to help the assistant fix it.

## Evaluation Process

1. First, read the task and identify what a correct solution requires.
2. Then, examine the output and note exactly what it does right and wrong.
3. Assign a score based on the rubric below.

## Rubric (score 0.0-1.0)

- 0.0-0.2: Completely wrong, unrelated to task, crashes, or is empty
- 0.3-0.5: Partially correct but has major bugs, missing requirements, or won't compile
- 0.6-0.8: Mostly correct with minor issues (missed edge cases, style violations)
- 0.9-1.0: Fully correct, handles edge cases, production-quality

IMPORTANT: Do NOT let the length of the output influence your score.
A short, correct answer beats a long, incorrect one. Be strict: if the
code would not run or would produce wrong output, score it below 0.3.

## Evaluation Criteria

{criteria_list}

## Coaching Reply (CRITICAL)

When the output is rejected (score < 0.7), your critique must be a coaching
reply that gives the assistant the BEST possible chance of succeeding on the
next attempt. A coaching reply must include:

1. **What was done well** — reinforce correct parts so they are kept
2. **What specific thing is wrong** — name the file, function, or line
3. **Why it's wrong** — what requirement does it violate?
4. **How to fix it** — give a concrete, specific fix (show corrected code
   or the exact change needed). Do NOT say "fix the bug" — say "change
   line X from Y to Z because..." or "add error handling for case W like this..."
5. **What to verify after fixing** — how the assistant should check the fix works

Be direct and specific. "The sort function doesn't handle None inputs — 
add `if lst is None: return []` at the top of the function" is a coaching
reply. "Missing edge cases" is not.

## Output Format

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{
  "score": 0.0,
  "critique": "COACHING REPLY: follow the 5-point structure above",
  "checks_passed": ["check_name"],
  "checks_failed": ["check_name"]
}
'''
        
        # Format the criteria list for the prompt
        criteria_list = "\n".join([f"{i+1}. {c}" for i, c in enumerate(criteria)])
        
        # Build the final prompt
        if self._prompt_template is not None:
            # Custom template — uses Python .format(), so {{literal}} for braces
            prompt = self._prompt_template.format(
                task=task, output=output, criteria_list=criteria_list
            )
        else:
            # Default template — uses .replace() so only {criteria_list} is replaced
            prompt = prompt_template.replace('{criteria_list}', criteria_list)
            # ── Known failure patterns ─────────────────────────────────
            if model_profile_key:
                known = get_known_failures(model_profile_key)
                if known:
                    failure_lines = [
                        "\n\n## Known Failure Patterns for This Model\n\n",
                        "The model that produced this output has known recurring issues.\n",
                        "Check specifically for these and mention them by name if found:\n\n",
                    ]
                    for kf in known:
                        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(kf.severity, "⚪")
                        failure_lines.append(
                            f"- {icon} **{kf.trigger_pattern()}**: {kf.feedback}\n"
                        )
                    prompt += "".join(failure_lines)
            # Inject the actual task and output (not in template placeholders)
            prompt += f"\n\n## Task to Evaluate\n\n{task}\n\n## Output to Evaluate\n\n{output}"
        
        # Prepare the messages for LLM call
        messages = [
            {"role": "system", "content": "You are a code quality judge. Evaluate the provided output against the task."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            # Call the judge LLM using OpenRouter API
            api_key = os.environ.get(self.model_config["env_var"])
            if not api_key:
                raise ValueError(f"API key not found: {self.model_config['env_var']}")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": OPENROUTER_REFERER,
                "X-Title": "Multi-Tier Orchestrator",
            }
            payload = {
                "model": self.model_config["model"],
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": 1024,
            }
            
            response = requests.post(
                f"{self.model_config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60  # Shorter timeout for judge calls
            )
            
            if response.status_code != 200:
                raise Exception(f"Judge API error: {response.status_code} - {response.text}")
            
            raw_response = response.json()["choices"][0]["message"]["content"]
            
        except Exception as e:
            # Handle any errors in the LLM call
            return Verdict(
                accepted=False,
                score=0.0,
                critique=f"Judge unavailable: {str(e)}",
                checks_passed=[],
                checks_failed=["judge_unavailable"]
            )
        
        try:
            # Try to parse JSON response
            # Guard against None or non-string responses from LLM
            if not raw_response or not isinstance(raw_response, str):
                return Verdict(
                    accepted=False,
                    score=0.0,
                    critique=f"Judge returned empty or non-string response: {type(raw_response).__name__}",
                    checks_passed=[],
                    checks_failed=["judge_unavailable"]
                )
            # First, try to extract JSON from the response if it's not directly valid JSON
            # Strip markdown code fences first
            json_str = raw_response.strip()
            fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', json_str, re.DOTALL)
            if fence_match:
                json_str = fence_match.group(1).strip()
            
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    data = json.loads(json_str)
                except (json.JSONDecodeError, ValueError):
                    # Retry: strip code fences and try again
                    stripped = json_str.strip()
                    if stripped.startswith('```'):
                        stripped = re.sub(r'^```(?:json)?\s*\n', '', stripped)
                        stripped = re.sub(r'\n```\s*$', '', stripped)
                        try:
                            data = json.loads(stripped)
                        except (json.JSONDecodeError, ValueError):
                            # Final attempt: try reparative parsing
                            # Common failure: literal newlines in JSON string values,
                            # or LLM outputs Python dict syntax instead of JSON
                            repaired = re.sub(
                                r'"([^"\\]*(?:\\.[^"\\]*)*)"',
                                lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\t', '\\t') + '"',
                                stripped
                            )
                            # Also fix single-quoted Python dicts (replace ' with ")
                            if repaired.startswith('{') and "'" in repaired[:50]:
                                repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)
                            try:
                                data = json.loads(repaired)
                            except (json.JSONDecodeError, ValueError):
                                return Verdict(
                                    accepted=False, score=0.0,
                                    critique=f"Malformed JSON from judge: {stripped[:300]}",
                                    checks_passed=[], checks_failed=["json_parse_error"]
                                )
                    else:
                        # Try reparative parsing on the original
                        repaired = re.sub(
                            r'"([^"\\]*(?:\\.[^"\\]*)*)"',
                            lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\t', '\\t') + '"',
                            json_str
                        )
                        if repaired.startswith('{') and "'" in repaired[:50]:
                            repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)
                        try:
                            data = json.loads(repaired)
                        except (json.JSONDecodeError, ValueError):
                            return Verdict(
                                accepted=False, score=0.0,
                                critique=f"Malformed JSON from judge: {json_str[:300]}",
                                checks_passed=[], checks_failed=["json_parse_error"]
                            )
            else:
                # If no JSON found, treat the whole response as critique
                data = {
                    "score": 0.0,
                    "critique": raw_response[:500],
                    "checks_passed": [],
                    "checks_failed": ["json_parse_error"]
                }
            
        except (json.JSONDecodeError, TypeError, ValueError):
            # If JSON parsing fails, return default verdict with raw response as critique
            return Verdict(
                accepted=False,
                score=0.0,
                critique=f"Failed to parse judge response: {str(raw_response)[:200]}",
                checks_passed=[],
                checks_failed=["json_parse_error"]
            )
        
        # Validate and return the verdict
        try:
            # Safely extract values with defaults
            score = float(data.get("score", 0.0))
            critique = str(data.get("critique", "No critique provided"))
            checks_passed = list(data.get("checks_passed", [])) if data.get("checks_passed") is not None else []
            checks_failed = list(data.get("checks_failed", [])) if data.get("checks_failed") is not None else []
            
            # Apply acceptance threshold - override the LLM's accepted value
            accepted = score >= self.acceptance_threshold
            
            verdict = Verdict(
                accepted=accepted,
                score=score,
                critique=critique,
                checks_passed=checks_passed,
                checks_failed=checks_failed
            )
            
            # Ensure score is within valid range
            verdict.score = max(0.0, min(1.0, verdict.score))
            
            return verdict
            
        except (KeyError, TypeError) as e:
            # If data structure is malformed, return default verdict
            return Verdict(
                accepted=False,
                score=0.0,
                critique=f"Malformed judge response: {raw_response}",
                checks_passed=[],
                checks_failed=["malformed_response"]
            )