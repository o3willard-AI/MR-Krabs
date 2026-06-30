# MR-Krabs Judge — Best Practices & Design

**Research basis:** LMSYS MT-Bench (Zheng et al., 2023), G-Eval (Liu et al., 2023),
JudgeLM (Zhu et al., 2023)

## Best Practice: Always Use a Reasoning Model

The Judge is the **quality gate for the entire escalation pipeline.** Its
reliability is the ceiling on the system's ability to distinguish good code from
bad. This is the highest-leverage model choice in the system.

**Rule:** Never use a small or general-purpose model for judging.

| Property | Reasoning Models | General-Purpose / Small Models |
|----------|-----------------|-------------------------------|
| Score calibration | Anchored to rubric | Drifts across calls |
| Critique specificity | Names files, lines, exact fixes | "Missing edge cases" |
| JSON reliability | Clean, parseable JSON consistently | Hallucinated fields, malformed JSON |
| Verbosity bias resistance | Follows "don't favor length" instruction | Longer = better, reliably |
| Position bias resistance | Minimal impact with swap instructions | Strong first-answer bias |

### Default Model

```
"Judge": {
    "model": "deepseek/deepseek-r1",
    "temperature": 0.1,
    "provider": "openrouter",
    "role": "judge"
}
```

Low temperature (0.1) is critical — judging is a deterministic task. Higher
temperatures introduce variance in scores and critique quality.

### Serving the Judge

We recommend running the Judge through OpenRouter (cloud) for reliability.
Local reasoning models on llama.cpp also work — see [MODEL_CONFIG.md](MODEL_CONFIG.md)
for llama.cpp provider configuration. We do **not** recommend LM Studio, Ollama,
or vLLM for the Judge due to known issues with reasoning-model content extraction.

### Why Not Fine-Tuned Judges?

JudgeLM and Prometheus show that fine-tuned Llama 7B–33B judges can achieve 90%+
agreement with GPT-4 teachers. This is a viable path for production deployment
where latency and cost are concerns. For MR-Krabs, we use an API model for
simplicity and quality, but fine-tuned judges are on the roadmap.

## Prompt Design

The default Judge prompt combines three proven patterns:

### 1. Impartial Judge Framing (LMSYS)

Opens with "You are an impartial code quality judge" — studies show this framing
produces more objective evaluations than "You are an expert" or "Evaluate this."

Includes explicit bias warnings:
- "Do NOT let the length of the output influence your score"
- "A short, correct answer beats a long, incorrect one"

### 2. Anchored Rubric (G-Eval)

Without anchoring, LLM judges produce inconsistent scores — the same quality
output might score 0.5 or 0.8 depending on the call. The anchored rubric eliminates
this drift:

```
0.0-0.2: Completely wrong, unrelated to task, crashes, or is empty
0.3-0.5: Partially correct but has major bugs, missing requirements, or won't compile
0.6-0.8: Mostly correct with minor issues (missed edge cases, style violations)
0.9-1.0: Fully correct, handles edge cases, production-quality
```

### 3. Structured Output Format

```
{
  "score": 0.0,
  "critique": "COACHING REPLY: follow the 5-point structure",
  "checks_passed": ["check_name"],
  "checks_failed": ["check_name"]
}
```

## Coaching Reply (Critical)

When the Judge rejects output, the critique is NOT just an error message — it is
fed back to the agent as a prompt for the next retry attempt. A good coaching
reply gives the agent its best possible chance to succeed.

### 5-Point Structure

Every coaching reply MUST include:

1. **What was done well** — reinforce correct parts so they are kept in the retry
2. **What specific thing is wrong** — name the exact file, function, or line number
3. **Why it's wrong** — which requirement or specification does it violate?
4. **How to fix it** — a concrete, specific change. Show the corrected code or
   the exact edit needed. Do NOT say "fix the bug" — say "change line 42 from
   `return x` to `return x.strip()` because the output must not have whitespace."
5. **What to verify after fixing** — how the agent should check that the fix
   actually works (specific test case, expected output)

### Good vs Bad Coaching

| Bad (Unactionable) | Good (Actionable) |
|---|---|
| "Missing edge cases" | "The function crashes on empty list. Add `if not lst: return 0` at line 5 and verify with `test_empty_input()`" |
| "Style issues" | "Uses camelCase instead of snake_case. Rename `getData` → `get_data` on lines 12 and 18" |
| "Not production ready" | "Missing type hints. Add `def solve(x: int) -> int:` on line 3 and docstring explaining what x represents" |
| "Security problem" | "SQL query on line 17 uses string formatting which allows injection. Replace with parameterized query: `cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))`" |

## Evaluation Criteria

### Default Criteria

Code tasks (auto-detected): `correctness`, `completeness`, `style`, `safety`, `production_ready`

QA tasks: `accuracy`, `completeness`, `clarity`, `helpfulness`

### Task Type Detection

`detect_task_type(task)` classifies tasks as "code" or "qa" based on keyword
presence: "write code", "implement", "function", "class", "method", "bug", "fix",
"refactor", "optimize", "algorithm", "compiles", "runs", "test".

At least 2 keyword matches are required to classify as "code" (prevents false
positives on general Q&A that happens to mention "test").

### Custom Criteria

Pass custom criteria when creating a Judge instance:

```python
judge = Judge(
    model="Judge",
    criteria=["does it compile", "no SQL injection", "handles Unicode"],
    acceptance_threshold=0.8,
)
```

### Custom Prompt Template

Override the entire judge prompt:

```python
judge = Judge()
judge.prompt_template = """
You are a security-focused code reviewer...
TASK: {task}
OUTPUT: {output}
CRITERIA: {criteria_list}
Return JSON: {{"score": 0.0, ...}}
"""
```

When using custom templates, use `{{` and `}}` for literal braces (Python
`.format()` escaping).

## Acceptance Threshold

Default: 0.7. Configurable per-instance:

```python
judge = Judge(acceptance_threshold=0.6)  # more lenient
judge = Judge(acceptance_threshold=0.9)  # stricter
```

Threshold should be tuned per use case:
- **0.6**: Rapid prototyping — accept "mostly works" code
- **0.7**: Standard development — accept code with minor issues
- **0.8+**: Production/strict — reject anything with known issues

## Infrastructure Note

The Judge connects to models via the same provider system as coder tiers.
We recommend llama.cpp for local models and OpenRouter for cloud models.
See [MODEL_CONFIG.md](MODEL_CONFIG.md) for provider configuration.

## Error Handling

The Judge is a network-dependent component. It handles failures gracefully:

- **Network error:** Returns `Verdict(accepted=False, critique="Judge unavailable: ...")`
- **API error (4xx/5xx):** Same degradation path
- **Malformed JSON from LLM:** Attempts regex extraction, falls back to treating
  the entire response as critique text
- **None/non-string response:** Guard clause returns `Verdict(accepted=False)`
  with error message
- **Missing API key:** Raises `ValueError` at construction time (fail fast)

All failures produce `checks_failed=["judge_unavailable"]` or
`checks_failed=["json_parse_error"]` — the orchestrator treats these as
rejections and continues the escalation loop.

## Research References

- **LMSYS MT-Bench** (Zheng et al., 2023): "Judging LLM-as-a-Judge with MT-Bench
  and Chatbot Arena" — established LLM judge reliability at 80%+ human agreement
- **G-Eval** (Liu et al., 2023): "G-Eval: NLG Evaluation using GPT-4 with Better
  Human Alignment" — chain-of-thought judging with anchored rubrics
- **JudgeLM** (Zhu et al., 2023): "JudgeLM: Fine-tuned Large Language Models are
  Scalable Judges" — 90%+ agreement with GPT-4 using fine-tuned 7B–33B judges
- **Prometheus** (Kim et al., 2024): Fine-tuned evaluator LM with detailed rubrics

## Key Files

| File | Purpose |
|------|---------|
| `src/core/judge.py` | Judge class, verdict dataclass, default prompt, evaluation logic |
| `src/core/judge_criteria.py` | Default criteria (CODE_CRITERIA, QA_CRITERIA), task type detection |
| `src/core/model_config.py` | MODELS["Judge"] — model selection, temperature, provider |
