# MR-Krabs roadmap

Living note for the next phase of work. Add new entries at the top.

## Next phase — Principal-agent bootstrap (2026-11-08)

The next section of improvements revolves around how a user works with the Principal agent to bootstrap into MR-Krabs. Two concrete sub-problems:

1. **Establishing the models to use** — which coder tiers (l0/l1/l2), judge, and planner models a deployment runs.
2. **Establishing the methods to connect to those models** — provider endpoints, API keys, and the llama.cpp / OpenRouter wiring (`~/.mrkrabs/config.yaml` today).

This is onboarding/configuration UX: the user and the Principal agent together arrive at a working `config.yaml`, rather than hand-editing it. It is not a coding-model change.
