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
from src.core.judge_criteria import CODE_CRITERIA, QA_CRITERIA, PLAN_CRITERIA, detect_task_type, MAX_CODER_TASK_KB, MAX_CODER_TASK_FILES, MAX_CODER_TASK_TESTS
from src.core.model_profiles import get_known_failures, KnownFailure


@dataclass
class Verdict:
    """Represents the verdict from a judge evaluation."""
    
    accepted: bool
    provisional: bool       # True → accepted with minor corrections needed
    score: float            # 0.0 - 1.0
    critique: str           # specific, actionable feedback with coaching  
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

    def _parse_json_response(
        self, raw_response: str, task: str, output: str
    ) -> dict | None:
        """Extract and parse JSON from a judge LLM response. (M4)

        Tries two strategies in order:
          1. Direct JSON parse with fence stripping
          2. Reparative parse (fix literal newlines, Python single-quote dicts)

        Returns parsed dict or None if all strategies fail (raw text fallback).
        """
        import json as _json

        if not raw_response or not isinstance(raw_response, str):
            return None

        json_str = raw_response.strip()

        # Strip markdown code fences if present
        fence_re = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL)
        fence_match = fence_re.search(json_str)
        if fence_match:
            json_str = fence_match.group(1).strip()

        # Extract the JSON object
        obj_re = re.compile(r'\{.*\}', re.DOTALL)
        obj_match = obj_re.search(json_str)
        if not obj_match:
            return None  # No JSON-like content at all

        json_str = obj_match.group(0)

        # Remove any remaining fence markers
        json_str = re.sub(r'^```(?:json)?\s*\n?', '', json_str)
        json_str = re.sub(r'\n?```\s*$', '', json_str)

        # --- Strategy 1: Direct parse ---
        try:
            return _json.loads(json_str)
        except (_json.JSONDecodeError, ValueError):
            pass

        # --- Strategy 2: Reparative parse ---
        # Fix literal newlines/tabs in JSON strings
        string_re = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"', re.DOTALL)
        repaired = string_re.sub(
            lambda m: '"' + m.group(1)
                .replace('\n', '\\n')
                .replace('\t', '\\t')
                .replace('\r', '\\r') + '"',
            json_str,
        )
        # Also fix Python single-quoted dicts (LLMs sometimes output {'key': 'val'})
        if repaired.startswith('{') and "'" in repaired[:50]:
            repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)

        try:
            return _json.loads(repaired)
        except (_json.JSONDecodeError, ValueError):
            return None  # All strategies exhausted

    
    def evaluate(self, task: str, output: str, model_profile_key: Optional[str] = None, spec: Optional[dict[str, list[str]]] = None) -> Verdict:
        """Evaluate code/text output against the specified task.
        
        Args:
            task: The original task description
            output: The output to evaluate
            model_profile_key: Optional model_profile_key for known-failure injection
            spec: Optional dict with 'success_criteria', 'constraints', 'anti_patterns'
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
            prompt_template = '''You are an impartial code quality judge. You evaluate code
produced by a PI coding agent — an LLM that writes complete files with
docstrings, type hints, and production-quality patterns.

PI output characteristics you should expect:
- Files may arrive in any order. Judge by content, not creation order.
- Minor cross-file inconsistencies (import paths, function signatures) are
  normal on multi-file tasks — score in the 0.6–0.8 range, not below 0.5.
- Truncated output is expected on large tasks. Score what was produced,
  not what was promised but missing. The pipeline salvages partial output.
- Docstrings and type hints are standard, not "unnecessary verbosity."

Your job is to evaluate whether the output correctly solves the given task
and — if it does not — provide specific, actionable coaching to help the
assistant fix it.

## Evaluation Process

1. First, read the task and identify what a correct solution requires.
2. Then, examine the output and note exactly what it does right and wrong.
3. Assign a score based on the rubric below.

## Rubric (score 0.0-1.0)

- 0.0-0.2: Completely wrong, unrelated to task, crashes, or is empty
- 0.3-0.5: Partially correct but has major bugs, missing requirements, or won't compile
- 0.6-0.8: Mostly correct with minor issues (missed edge cases, style violations)
- 0.9-1.0: Fully correct, handles edge cases, production-quality

## Provisional Accept (score 0.75–0.85)

When the output is substantially correct but has small, targeted issues
(truncation, missing one edge case, minor oversight in one file), set
`\"provisional\": true` and provide corrections. This tells the coder:
\"Your work is good — don't rewrite it. Just apply these specific fixes.\"

Provisional accept means:
- The coder keeps its existing code and makes ONLY the corrections you list
- The coder returns for final verification (one additional evaluation)
- The total retry cost is minimal — a few lines, not a full rewrite

Use provisional accept for: missing docstrings, missed edge case in one function,
truncated output at the end of the last file, style violations in one file,
a single missing import. Do NOT use it for: wrong architecture, missing whole
files, code that doesn't compile, security vulnerabilities.

IMPORTANT: Do NOT let the length of the output influence your score.
A short, correct answer beats a long, incorrect one. Be strict: if the
code would not run or would produce wrong output, score it below 0.3.

## Evaluation Criteria

{criteria_list}

## Coder Task Size Limits (for plan evaluations ONLY)

When evaluating a PLAN (not code), you MUST check that each coder task is
small enough for the PI coding agent to execute successfully:

- Each coder task MUST be under {MAX_CODER_TASK_KB}KB (about 750 words of instruction)
- Each coder task MUST create/modify at most {MAX_CODER_TASK_FILES} files
- Each coder task MUST contain at most {MAX_CODER_TASK_TESTS} test functions
- Multi-file tasks with 5+ files or large test suites MUST be split further

If any task in the plan exceeds these limits, REJECT the plan with score < 0.4.
In your critique, specify exactly WHICH task is too large and HOW to split it.

These limits exist because PI's write tool has a content cap — oversized
tasks get truncated and produce broken code. A plan that looks good but
exceeds these limits WILL fail when executed. Rejecting it here saves
cycles. Size violations are NOT \"minor issues\" — score them as major.

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

## Integration Checks (check these explicitly)

Beyond correctness, verify that the implementation is actually COMPLETE and WIRED:

1. **Call-site verification**: For each function the task requires, verify it
   is actually CALLED somewhere in the execution path. A function that exists
   but is never invoked (dead code) is a FAILURE — score ≤0.5 even if the
   function body is correct. Flag with check: "dead_function_<name>".

2. **Stub/mock detection**: Scan for placeholder indicators: "TODO", "FIXME",
   "placeholder", "stub", "mock data", "for now", "simplified version",
   "in a real implementation", "# skip". Any of these mean the implementation
   is INCOMPLETE — score ≤0.4. Flag with check: "stub_detected".

3. **Dependency constraints**: If the task says "stdlib only" or "zero external
   dependencies", verify ALL imports are from Python's standard library.
   External imports (requests, pytest for non-test files, etc.) when the
   spec forbids them is a FAILURE — score ≤0.3. Flag with: "constraint_violation".

4. **Error-path integrity**: For critical operations (filesystem writes, network
   calls, data mutations), verify that except blocks contain recovery actions
   (raise, log, rollback, return error) — not just bare `pass` or `continue`.
   Silent error swallowing in critical paths is a FAILURE — score ≤0.5.
   Flag with: "swallowed_error_<line>".

These integration checks are AS IMPORTANT as correctness checks. A
functionally correct function that is never called is useless. A "working"
proxy that returns mock data is not working. Deduct severely for these.

## Output Format

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{
  "score": 0.0,
  "provisional": false,
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
            prompt = prompt.replace('{MAX_CODER_TASK_KB}', str(MAX_CODER_TASK_KB))
            prompt = prompt.replace('{MAX_CODER_TASK_FILES}', str(MAX_CODER_TASK_FILES))
            prompt = prompt.replace('{MAX_CODER_TASK_TESTS}', str(MAX_CODER_TASK_TESTS))
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
            # ── Structured task contract (Article Section 4) ────────────
            if spec:
                spec_lines = ["\n\n## Acceptance Criteria\n\n"]
                if spec.get("success_criteria"):
                    spec_lines.append("**Must satisfy ALL of:**\n")
                    for i, criterion in enumerate(spec["success_criteria"], 1):
                        spec_lines.append(f"{i}. {criterion}\n")
                if spec.get("constraints"):
                    spec_lines.append("\n**Must NOT violate:**\n")
                    for i, constraint in enumerate(spec["constraints"], 1):
                        spec_lines.append(f"{i}. {constraint}\n")
                if spec.get("anti_patterns"):
                    spec_lines.append("\n**Known anti-patterns (score < 0.5 if matched):**\n")
                    for i, ap in enumerate(spec["anti_patterns"], 1):
                        spec_lines.append(f"{i}. {ap}\n")
                prompt += "".join(spec_lines)
            # Inject the actual task and output (not in template placeholders)
            prompt += f"\n\n## Task to Evaluate\n\n{task}\n\n## Output to Evaluate\n\n{output}"
        
        # Prepare the messages for LLM call
        messages = [
            {"role": "system", "content": "You are a code quality judge. Evaluate the provided output against the task."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            # Call the judge LLM — supports both hardcoded api_key and env var
            api_key = self.model_config.get("api_key") or os.environ.get(
                self.model_config.get("env_var") or ""
            )
            if not api_key:
                raise ValueError(
                    f"No API key configured for judge ({self.model_config.get('provider', '?')})"
                )
            
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
                provisional=False,
                score=0.0,
                critique=f"Judge unavailable: {str(e)}",
                checks_passed=[],
                checks_failed=["judge_unavailable"]
            )
        
        try:
            data = self._parse_json_response(raw_response, task, output)
            if data is None:
                # Non-JSON response — treat raw text as critique
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
                provisional=False,
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
                
            # Extract provisional flag — score 0.75-0.85 auto-triggers provisional
            # unless the LLM explicitly set it
            provisional = bool(data.get("provisional", False))
            if not provisional and 0.75 <= score < self.acceptance_threshold:
                provisional = True
                
            # Apply acceptance threshold
            accepted = score >= self.acceptance_threshold
                
            verdict = Verdict(
                accepted=accepted,
                provisional=provisional,
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
                provisional=False,
                score=0.0,
                critique=f"Malformed judge response: {raw_response}",
                checks_passed=[],
                checks_failed=["malformed_response"]
            )