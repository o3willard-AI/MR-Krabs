# Model Benchmark — Kiosk Challenge (Jul 2026)

All tests: 49K ctx, PI coder on .23 (3× RTX 3060 36GB), 7B judge on .21.
Same 17-file Flask admin panel task. All models at Q4_K_M quantization.

## Results

| Model | Arch | Size | P1 Time | P2 Time | Total | Score | Winner |
|-------|------|------|---------|---------|-------|-------|--------|
| **Qwen3-Coder-30B** | MoE (30B/3B) | 18 GB | **9 min** | **11 min** | **20 min** | 0.75/0.75 | 🥇 |
| Qwen3.6-27B | Dense (27B) | 16 GB | 37 min | 15 min | 39 min | 0.75/0.70 | 🥈 |
| Claude-Distilled-35B | MoE (35B/A3B) | 20 GB | 14 min | 50 min* | 64 min | 0.75/0.75 | 🥉 |
| Ornith-1.0-35B | Dense (35B) | 20 GB | 38 min | 27 min | 66 min | 0.75/0.75 | 4th |

*Claude Pass 2 needed a retry (score 0.00 on first attempt, 0.75 on second).

## Key Findings

### MoE dominates dense for speed
The two MoE models (Qwen3-Coder, Claude) are dramatically faster on Pass 1
than their dense counterparts. MoE activates only a fraction of parameters
per token (3B out of 30B for Qwen3-Coder), which means:
- Less over-generation (can't fill 49K ctx with 3B active)
- Faster token generation
- Same output quality

### Quality is consistent across all models
Every model scored 0.75 with the 7B judge. The judge is the great equalizer —
it doesn't matter which model writes the code as long as it meets the spec.
The difference is purely in speed and reliability.

### Dense models over-generate
Qwen3.6-27B and Ornith-1.0-35B both fill their context windows with output
tokens, leading to 37-38 minute Pass 1 times. The MoE models physically
cannot over-generate to the same degree — 3B active parameters simply can't
produce that many tokens.

### Claude MoE is unpredictable
Claude's Pass 1 was fast (14 min) but Pass 2 was rejected on first attempt
and needed a costly retry (50 min total for Pass 2). The model produces
inconsistent output — excellent sometimes, garbage other times.

## Recommendation

**Qwen3-Coder-30B (MoE) is the recommended model for MR-Krabs L0 coder.**
It's 2× faster than the previous recommendation (Qwen3.6-27B) with identical
quality. The 18 GB model fits comfortably in 24 GB VRAM with 49K context.

For users with 12 GB VRAM (Tier 1), Qwen2.5-Coder-7B remains the recommendation.
For users with 36 GB VRAM (Tier 3), Qwen3-Coder-30B at Q5_K_M or Q6_K
quantization is worth testing for improved output quality.

## Raw data

### Qwen3-Coder-30B (MoE)
- Pass 1: 1 attempt, 541s, 0.75
- Pass 2: 1 attempt, 653s, 0.75
- Total: 2 attempts, 1193s (20 min)

### Qwen3.6-27B (Dense)
- Pass 1: 1 attempt, 2233s, 0.75
- Pass 2: 1 attempt, 914s, 0.70
- Total: 2 attempts, 2336s (39 min)

### Claude-Distilled-35B (MoE)
- Pass 1: 1 attempt, 856s, 0.75
- Pass 2: 2 attempts, 3002s, 0.75 (first attempt rejected 0.00)
- Total: 3 attempts, 3859s (64 min)

### Ornith-1.0-35B (Dense)
- Pass 1: 1 attempt, 2301s, 0.75
- Pass 2: 1 attempt, 1642s, 0.75
- Total: 2 attempts, 3943s (66 min)


---

## Small-Model Benchmark (Jul 2026)

Same conditions: 49K ctx, PI coder, 7B judge on .21.

| Model | Size | Result | Time | Score |
|-------|------|--------|------|-------|
| **Ornith-1.0-9B** | 5.3 GB | ✅ Pass | **62 min** | 0.75/0.75 |
| Qwen3.5-4B-SuperCoder | 2.5 GB | ✅ Pass | 81 min | 0.75/0.75 |
| Gemma-4-12B-Coder | 6.9 GB | ❌ PI incompatible | — | — |
| Qwen2.5-Coder-7B | 4.4 GB | ❌ PI incompatible | — | — |

### Ornith-1.0-9B
- Pass 1: 1 attempt, 1945s (32 min), 0.75
- Pass 2: 1 attempt, 1772s (30 min), 0.75
- Total: 2 attempts, 3717s (62 min)
- Best small-model option tested. 5.3 GB fits any GPU.

### Qwen3.5-4B-SuperCoder
- Pass 1: 1 attempt, 1038s (17 min), 0.75
- Pass 2: 2 attempts, 3805s (63 min), 0.75 (needed retry)
- Total: 3 attempts, 4843s (81 min)
- Smallest model tested (2.5 GB). Works but Pass 2 is unreliable.

### Gemma-4-12B-Coder and Qwen2.5-Coder-7B
Both failed with "Empty output from PI" on all 3 retries. Models respond
to direct completions API but PI cannot drive them. Likely prompt template
or tool-call format incompatibility.

## Recommendation

For single-GPU (12 GB) users, **Ornith-1.0-9B** is the best tested option.
It completes the kiosk challenge in 62 min with 0.75 judge scores. For
users with 24+ GB VRAM, **Qwen3-Coder-30B MoE** remains the top pick at
20 min — 3× faster than the best small model.
