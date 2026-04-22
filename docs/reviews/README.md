# Peer Review Instructions for LLM Reviewers

## How to Use This Directory

This directory contains **targeted review requests** for different aspects of the Cost-Optimized AI Orchestration project. Each document is designed for a specific type of reviewer (human or LLM) to focus on a specific dimension of the design.

---

## Review Documents

| Document | Focus Area | Best For |
|----------|-----------|----------|
| `PEER_REVIEW_REQUEST.md` | Overall architecture, completeness, contradictions | General architecture review |
| `SECURITY_REVIEW_REQUEST.md` | Vulnerabilities, privacy, attack vectors | Security-focused review |
| `DX_REVIEW_REQUEST.md` | Developer experience, usability, frustration points | Developer-focused review |
| `PERFORMANCE_REVIEW_REQUEST.md` | Latency, concurrency, scaling, bottlenecks | Performance-focused review |

---

## How to Review

### Step 1: Read the Context

Start by reading these documents in order:

1. `../COST_OPTIMIZED_ORCHESTRATION_SUMMARY.md` — Executive overview (10 min)
2. `../prd/COST_OPTIMIZED_ORCHESTRATION_PRD.md` — Product requirements (15 min)
3. `../architecture/SYSTEM_ARCHITECTURE.md` — System architecture (20 min)
4. `../architecture/TECHNICAL_DESIGN_DECISIONS.md` — Technical designs (20 min)
5. `../IMPLEMENTATION_ROADMAP.md` — Implementation plan (10 min)

Total context reading: ~75 minutes.

### Step 2: Read the Relevant Review Request

Pick the review document that matches your expertise:

- **General architecture?** → `PEER_REVIEW_REQUEST.md`
- **Security?** → `SECURITY_REVIEW_REQUEST.md`
- **Developer experience?** → `DX_REVIEW_REQUEST.md`
- **Performance?** → `PERFORMANCE_REVIEW_REQUEST.md`

### Step 3: Write Your Review

Follow the structure suggested in the review request document. Be:

- **Specific**: Reference exact line numbers, file names, and quotes
- **Constructive**: Don't just identify problems — suggest solutions
- **Honest**: If something looks good, say so. If something looks wrong, say so clearly
- **Prioritized**: Distinguish between "must fix" and "nice to have"

### Step 4: Format Your Review

Save your review as a new file in this directory:

```
REVIEW_[TYPE]_[DATE].md
```

Examples:
- `REVIEW_ARCHITECTURE_2026-04-03.md`
- `REVIEW_SECURITY_2026-04-03.md`
- `REVIEW_DX_2026-04-03.md`
- `REVIEW_PERFORMANCE_2026-04-03.md`

---

## What Makes a Great Review

### Great Reviews Include:

- **Specific references**: "In SYSTEM_ARCHITECTURE.md line 193, the `simplify()` function is underspecified because..."
- **Contradiction spotting**: "The PRD says X but the Architecture says Y. Which is correct?"
- **Missing edge cases**: "What happens when [specific scenario]?"
- **Real-world experience**: "I built something similar at [company] and we learned that..."
- **Concrete alternatives**: "Instead of X, consider Y because..."
- **Prioritized findings**: "Critical: ... High: ... Medium: ... Low: ..."

### Mediocre Reviews Include:

- Vague praise or criticism without specifics
- Feature requests that don't consider scope
- Generic advice that applies to any project
- Surface-level observations that don't probe the design

---

## Key Project Principles to Keep in Mind

When reviewing, remember:

1. **Free forever** — No business model, no premium features, no upsell. Suggestions that add complexity for monetization are not aligned with the mission.

2. **Integration over replacement** — We work with existing frameworks. Suggestions to build a competing framework are not aligned.

3. **Simplicity over completeness** — We'd rather do 3 things well than 10 things adequately. Suggestions that add significant scope should be questioned.

4. **Developer-first** — If it's hard to integrate or confusing to use, we've failed.

5. **Transparency** — Users should understand why decisions are made.

---

## Common Review Pitfalls to Avoid

1. **"Build your own framework instead"** — We've explicitly chosen integration. This is not up for debate.

2. **"Add a premium tier"** — This project is free forever. Not happening.

3. **"Use [specific technology] instead"** — Technology choices should be evaluated on merits, not preferences. Explain why, don't just name-drop.

4. **"This is too ambitious"** — Scope feedback is welcome, but be specific about what to cut and why.

5. **"This is not ambitious enough"** — Ambition feedback is welcome, but be specific about what to add and why it serves the mission.

---

## What Happens After Reviews

Reviews will be:
1. Consolidated into a findings document
2. Prioritized by severity
3. Addressed in design updates
4. Tracked as issues in the project

Your review directly shapes the quality of the final software. Thank you for your time and expertise.
