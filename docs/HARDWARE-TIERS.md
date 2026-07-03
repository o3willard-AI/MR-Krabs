# Hardware Tiers & Model Guidance

MR-Krabs runs entirely on local hardware — no cloud required for L0. The same
model handles all three roles (coder, judge, orchestrator). Choose your tier
based on available VRAM.

## Quick Reference

| Tier | VRAM | Model | Context | Files/pass | L0 Success | Cost/run |
|------|------|-------|---------|------------|------------|----------|
| **Entry** | 12 GB | Qwen2.5-Coder-7B Q4 | 32K | 3-5 | ~70% | $0 |
| **Standard** | 24 GB | Qwen3.6-27B Q4 | 49K | 11 | ~75% | $0 |
| **Advanced** | 36 GB | Qwen3.6-35B Q4 | 65K+ | 15+ | ~85% | $0 |

All tiers use the **same single-model architecture**: one llama.cpp server
handles coder (via PI), judge, and orchestrator. Peer judging produces
calibrated scores — no need for a separate judge model.

---

## Tier 1: Entry (12 GB VRAM, 1 GPU)

**Best for:** Getting started, simple coding tasks, single-file projects,
evaluating whether MR-Krabs fits your workflow.

### Hardware
- 1× GPU with 12 GB VRAM (RTX 3060, RTX 4070, A2000, or equivalent)
- 16 GB system RAM
- 50 GB disk space

### Model: Qwen2.5-Coder-7B-Instruct (Q4_K_M)

A purpose-built coding model. 7B parameters, Q4_K_M quantization.
~4.7 GB on disk, ~7 GB VRAM at 32K context.

```bash
# Download
cd /opt/llama.cpp/models
wget https://huggingface.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf
```

### llama.cpp server

```bash
/opt/llama.cpp/llama-server \
  -m /opt/llama.cpp/models/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 1234 \
  --n-gpu-layers 99 --ctx-size 32768 --batch-size 2048
```

Create a systemd unit for persistence:
```ini
# /etc/systemd/system/llama-server.service
[Unit]
Description=llama.cpp inference server (Qwen2.5-Coder-7B)
After=network-online.target

[Service]
Type=simple
User=root
ExecStart=/opt/llama.cpp/llama-server \
  -m /opt/llama.cpp/models/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 1234 \
  --n-gpu-layers 99 --ctx-size 32768 --batch-size 2048
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### MR-Krabs config

```yaml
# ~/.mrkrabs/config.yaml
version: "1.0"

providers:
  local:
    type: openai_compatible
    base_url: "http://localhost:1234/v1"
    api_key: "dummy"
    timeout: 1800

models:
  judge:
    provider: local
    model: "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
    temperature: 0.1
    max_tokens: 8192
    roles: [judge]

  l0-coder:
    provider: local
    model: "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
    temperature: 0.0
    max_tokens: 16384
    roles: [coder]
    tools: [file_write, file_read]

  orchestrator:
    provider: local
    model: "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
    temperature: 0.0
    max_tokens: 16384
    roles: [orchestrator]

  principal:
    roles: [principal]

pi_models:
  l0-coder: local/Qwen2.5-Coder-7B-Instruct-Q4_K_M

pi_timeouts:
  l0-coder: 1200

workflows:
  code:
    tiers: [l0-coder, principal]
    max_retries_per_tier: 3
    judge_model: judge

tier_failure_actions:
  l0-coder: log_only
```

### What to expect

| Scenario | Performance |
|----------|------------|
| Single file (<200 lines) | ~15-30 seconds, 90%+ acceptance |
| 2-3 files | ~1-3 minutes, 80% acceptance |
| 5+ files | Multi-pass with re-split, may need 2-3 retries |
| Complex HTML/CSS/JS | Works but slower — expect 2-3 min/file |
| Judge evaluation | ~5-15 seconds per verdict |

**Upgrade path:** Add a second GPU → jump to Tier 2 (Standard). Same config
structure, just point `base_url` to the 27B server and update model names.

---

## Tier 2: Standard (24 GB VRAM, 2 GPUs)

**Best for:** Daily driver. Multi-file projects, full-stack apps, the
configuration we use internally.

### Hardware
- 2× GPU with 12 GB each (dual RTX 3060, or equivalent)
- 24 GB system RAM
- 100 GB disk space

### Model: Qwen3.6-27B (Q4_K_M)

27B parameters, Q4_K_M quantization. ~16 GB on disk, ~20 GB VRAM at 49K context.
This is our **proven daily-driver config** — 17-file kiosk challenge completed in
39 minutes at $0.

```bash
# Download
cd /opt/llama.cpp/models
wget https://huggingface.co/bartowski/Qwen3.6-27B-GGUF/resolve/main/Qwen3.6-27B-Q4_K_M.gguf
```

### llama.cpp server

```bash
/opt/llama.cpp/llama-server \
  -m /opt/llama.cpp/models/Qwen3.6-27B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 1234 \
  --n-gpu-layers 99 --ctx-size 49152 --batch-size 2048
```

**Important:** Always run with `--reasoning off` if using a reasoning-capable
model. Reasoning models produce 95%+ `reasoning_content` tokens; the adapter
only reads `content` → near-empty output for non-judge roles. Our Qwen3.6-27B
server runs without the `--reasoning` flag at all (non-reasoning mode).

Systemd unit:
```ini
[Unit]
Description=llama.cpp inference server (Qwen3.6-27B)
After=network-online.target

[Service]
Type=simple
User=root
ExecStart=/opt/llama.cpp/llama-server \
  -m /opt/llama.cpp/models/Qwen3.6-27B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 1234 \
  --n-gpu-layers 99 --ctx-size 49152 --batch-size 2048
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### MR-Krabs config

See [`reference-configs/winning-config-jul2026.yaml`](reference-configs/winning-config-jul2026.yaml)
for the full config. Key points:

- All three roles on the same model
- PI as coder backend (11 files/pass)
- Judge threshold: 0.7 with provisional accept at 0.75-0.85
- 3 retries per tier, LOG_ONLY failure action for L0

### What to expect

| Scenario | Performance |
|----------|------------|
| Single file | ~30-60 seconds |
| 2-3 files | ~2-5 minutes |
| 11 files (one pass) | ~37 minutes (model-limited, see below) |
| 17 files (kiosk challenge) | 2 passes, ~39 minutes, 0.75/0.70 scores |
| Judge evaluation | ~10-60 seconds per verdict |

**Performance note:** At 49K context, Qwen3.6-27B massively over-generates.
An 11-file pass produces ~44K tokens (at 20 tok/s = 37 min). For faster
iteration on smaller tasks, reduce `--ctx-size` to 16384 — this bounds
generation to ~3-4 min/pass at the cost of smaller pass sizes.

### Upgrade path

Add a third GPU → Tier 3 (Advanced). Run larger models (35B) at higher context,
or run coder and judge on separate models to eliminate single-server contention.

---

## Tier 3: Advanced (36 GB VRAM, 3 GPUs)

**Best for:** Production deployment, large codebases, minimal cloud escalation.

### Hardware
- 3× GPU with 12 GB each (triple RTX 3060, or equivalent)
- 32 GB system RAM
- 150 GB disk space

### Option A: Single large model (35B Q4)

Run Qwen3.6-35B Q4_K_M (~20 GB on disk, ~28 GB VRAM at 65K context).
Larger model handles more complex tasks in fewer passes.

```bash
wget https://huggingface.co/bartowski/Qwen3.6-35B-A3B-GGUF/resolve/main/Qwen3.6-35B-A3B-Q4_K_M.gguf

/opt/llama.cpp/llama-server \
  -m /opt/llama.cpp/models/Qwen3.6-35B-A3B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 1234 \
  --n-gpu-layers 99 --ctx-size 65536 --batch-size 2048
```

### Option B: Dedicated coder + judge (dual-model)

Keep 27B Q4 for coder (.23, ports 1234) and add a separate 7-9B judge on
port 1235. Eliminates single-server contention (judge never waits for coder).

```yaml
models:
  judge:
    provider: local-judge
    model: "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
    temperature: 0.1
    max_tokens: 8192
    roles: [judge]

  l0-coder:
    provider: local-coder
    model: "Qwen3.6-27B-Q4_K_M"
    temperature: 0.0
    max_tokens: 32768
    roles: [coder]

providers:
  local-coder:
    type: openai_compatible
    base_url: "http://localhost:1234/v1"
    api_key: "dummy"
  local-judge:
    type: openai_compatible
    base_url: "http://localhost:1235/v1"
    api_key: "dummy"
```

### Option C: Higher quantization

Run 27B at Q6_K (~22 GB) for better output quality at the same speed.
Worth it if your primary bottleneck is judge acceptance rate, not speed.

### What to expect

| Scenario | Performance |
|----------|------------|
| 17 files | 1-2 passes, ~20-40 minutes (35B) or ~15-25 min (dual-model) |
| 30+ files | 3-5 passes, re-split cascade handles automatically |
| Judge timeout risk | Eliminated with dual-model setup |
| L0 success rate | ~85% (35B) or ~90% (dual-model) |

---

## Model Selection Guidelines

### Which model for which role?

| Role | Small (7-9B) | Medium (27B) | Large (35B) |
|------|-------------|-------------|------------|
| **Coder** | Single files, simple tasks | Multi-file, daily driver | Large projects, complex logic |
| **Judge** | ✅ Good (proportional to 7B coder) | ✅ Good (proportional to 27B coder) | ⚠️ Too strict for 27B coder |
| **Orchestrator** | ✅ Fine (task decomposition is lightweight) | ✅ Fine | ✅ Fine (but expensive in VRAM) |

**Critical rule:** The judge must be proportional to the coder. A 35B judge
scoring 27B output creates an impossible quality bar (documented: 0.00 vs 0.75
for identical output). Same-model judging produces calibrated scores.

### What about cloud models?

All three tiers support cloud escalation (L1/L2) via OpenRouter. The local
L0 handles routine tasks; cloud models catch what L0 can't. This keeps costs
near zero while providing a safety net. Configure `l1-coder` and `l2-coder`
in your config to enable escalation.

### Disk space needed

| Model | Q4_K_M size |
|-------|------------|
| Qwen2.5-Coder-7B | 4.7 GB |
| Qwen3.6-27B | 15.6 GB |
| Qwen3.6-35B (A3B) | 19.8 GB |

Plan for 2-3× model size in free disk space for downloads and temporary files.
