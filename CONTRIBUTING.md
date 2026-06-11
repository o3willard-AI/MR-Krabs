# Contributing

MR-Krabs is a config-driven, judge-gated multi-tier coding agent. Contributions
that preserve config-driven design are welcome.

## Architecture Rules

- **No hardcoded models.** Model names, provider URLs, and API keys live in
  `~/.mrkrabs/config.yaml` only. Source code must never reference a specific
  model, provider endpoint, or API key.
- **Config over code.** New features should be configurable. If a behavior
  belongs in the user's domain (which model to use, what threshold to accept),
  it goes in config.yaml, not a constant.
- **Judge is the quality gate.** Changes to the judge prompt or criteria must
  be backed by before/after score data on a known task set.

## Development Setup

```bash
git clone https://github.com/o3willard-AI/MR-Krabs.git
cd MR-Krabs
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing

```bash
# Unit tests (fast, no network)
python -m pytest tests/unit/ -q

# All tests including integration
python -m pytest tests/ -q

# Template validation
python -m src.validators.templates

# Config + connectivity check
python -m src.validators.startup
```

All changes must pass the full test suite. Add tests for new behavior.

## Commit Style

- `feat(scope): what changed`
- `fix(scope): what was fixed`
- `test(scope): what was tested`
- `docs(scope): what was documented`

Scopes: `pipeline`, `judge`, `config`, `templates`, `tests`, `docs`

## Pull Requests

1. Branch from `main`
2. Add tests covering the change
3. Run `python -m pytest tests/ -q` — must pass
4. Run `python -m src.validators.templates` — must pass
5. Keep PRs focused — one concern per PR

## Docs

When adding or changing features, update the relevant docs:
- User-facing changes → [README.md](README.md) or [docs/](docs/)
- New config options → [docs/MODEL_CONFIG.md](docs/MODEL_CONFIG.md)
- New env vars → [docs/COOKBOOK.md](docs/COOKBOOK.md)
- Common failure modes → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
