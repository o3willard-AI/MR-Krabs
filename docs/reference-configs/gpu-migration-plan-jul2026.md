# GPU Migration Plan — Jul 3, 2026

## Current state

| Machine | GPUs | VRAM | Model | Context | Role |
|---------|------|------|-------|---------|------|
| .21 | 2× 3060 12GB | 24 GB | Claude-Distilled-35B Q4 | 32K | Idle |
| .23 | 2× 3060 12GB | 24 GB | Qwen3.6-27B Q4 | 49K | All roles |

## Target state

| Machine | GPUs | VRAM | Model | Context | Role |
|---------|------|------|-------|---------|------|
| .21 | 1× 3060 12GB | 12 GB | Qwen2.5-Coder-7B Q4 | 32K | Tier 1 demo / spare judge |
| .23 | 3× 3060 12GB | 36 GB | Qwen3.6-27B Q4 (keep) | 65K | All roles (primary) |

## .21 post-move setup

1. Remove the 35B model (no longer fits):
   ```bash
   rm /opt/llama.cpp/models/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled.Q4_K_M.gguf
   ```

2. Download Qwen2.5-Coder-7B:
   ```bash
   cd /opt/llama.cpp/models
   wget https://huggingface.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf
   ```

3. Update systemd unit:
   ```ini
   ExecStart=/opt/llama.cpp/llama-server \
     -m /opt/llama.cpp/models/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
     --host 0.0.0.0 --port 1234 \
     --n-gpu-layers 99 --ctx-size 32768 --batch-size 2048
   ```

4. Restart: `systemctl restart llama-server`

## .23 post-move setup

1. Verify 3 GPUs visible: `nvidia-smi` should show 3× RTX 3060

2. Update systemd unit — bump context to 65K:
   ```ini
   ExecStart=/opt/llama.cpp/llama-server \
     -m /opt/llama.cpp/models/Qwen3.6-27B-Q4_K_M.gguf \
     --host 0.0.0.0 --port 1234 \
     --n-gpu-layers 99 --ctx-size 65536 --batch-size 2048
   ```

3. Restart: `systemctl restart llama-server`

4. Optional: also serve the 35B from the old .21 model (if disk space allows):
   ```bash
   # scp the 35B model from .21 before deleting it
   scp sblanken@192.168.101.21:/opt/llama.cpp/models/*35B*.gguf /opt/llama.cpp/models/
   ```

## MR-Krabs config changes

After migration, only one change needed:
- `~/.mrkrabs/config.yaml` stays the same (.23 is still the primary)
- .21 becomes available as `local-21` provider for Tier 1 testing or as a
  dedicated judge instance (see HARDWARE-TIERS.md Tier 3 Option B)

## MR-Krabs config changes

### Option A: Stay single-model on .23 (recommended)
No config changes needed. .23 is still the primary. .21 becomes available
for Tier 1 testing or as a dedicated judge.

### Option B: Dedicated judge on .21 (eliminates judge timeout risk)
```yaml
providers:
  local-23:
    type: openai_compatible
    base_url: "http://192.168.101.23:1234/v1"
    api_key: "dummy"
    timeout: 1800
  local-21:
    type: openai_compatible
    base_url: "http://192.168.101.21:1234/v1"
    api_key: "dummy"
    timeout: 300

models:
  judge:
    provider: local-21
    model: "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
    temperature: 0.1
    max_tokens: 8192
    roles: [judge]
```

This puts the judge on a separate server — no more single-server bottleneck.
7B judge is proportional to 27B coder (peer-class judging).
