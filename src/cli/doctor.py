#!/usr/bin/env python3
"""mrkrabs doctor — validate model connectivity and configuration.

Checks:
  1. Config file exists and is valid YAML
  2. Every provider endpoint is reachable
  3. Every model can produce a response (basic health check)
  4. API keys are set for providers that need them
  5. Workflow tiers reference defined models
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _status(ok: bool) -> str:
    return "✓" if ok else "✗"


def _load_config_safe() -> Tuple[Any, List[str]]:
    """Load config or return (None, [errors])."""
    from src.core.config_loader import load_config, ConfigNotFoundError

    errors: List[str] = []
    try:
        config = load_config()
        return config, errors
    except ConfigNotFoundError:
        errors.append("No config.yaml found and no legacy models available.")
        errors.append("Run the setup wizard: your principal agent should walk you")
        errors.append("through defining each role. See docs/SETUP_PROMPT.md")
        return None, errors
    except Exception as e:
        errors.append(f"Failed to load config: {e}")
        return None, errors


def check_config_file(config) -> List[str]:
    """Check that the config file exists and is valid."""
    issues: List[str] = []
    if config is None:
        return issues  # already reported

    if config.config_path and config.config_path.exists():
        print(f"  {_status(True)} Config file: {config.config_path}")
    else:
        print(f"  {_status(True)} Config: auto-generated from legacy models")

    return issues


def check_providers(config) -> List[str]:
    """Check each provider's connectivity."""
    issues: List[str] = []

    if config is None:
        return issues

    for name, provider in config.providers.items():
        if provider.is_principal:
            continue

        api_key = None
        if provider.api_key_env:
            api_key = os.environ.get(provider.api_key_env)
        elif provider.api_key:
            api_key = provider.api_key

        # Try to reach the models endpoint
        try:
            url = provider.base_url.rstrip("/") + "/models"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    model_count = len(data.get("data", []))
                    print(f"  {_status(True)} Provider '{name}': {model_count} models available")
                else:
                    print(f"  {_status(False)} Provider '{name}': HTTP {resp.status}")
                    issues.append(f"Provider '{name}' returned HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            print(f"  {_status(False)} Provider '{name}': HTTP {e.code} — check API key")
            issues.append(f"Provider '{name}' returned HTTP {e.code} — check {provider.api_key_env or 'API key'}")
        except Exception as e:
            print(f"  {_status(False)} Provider '{name}': {e}")
            issues.append(f"Provider '{name}' unreachable: {e}")

    return issues


def check_api_keys(config) -> List[str]:
    """Check that required API keys are set."""
    issues: List[str] = []

    if config is None:
        return issues

    checked = set()
    for model in config.models.values():
        provider_name = model.provider
        if not provider_name or provider_name in checked:
            continue
        checked.add(provider_name)

        provider = config.providers.get(provider_name)
        if not provider or provider.is_principal:
            continue

        if provider.api_key_env:
            key = os.environ.get(provider.api_key_env)
            if key:
                print(f"  {_status(True)} API key '{provider.api_key_env}': set")
            else:
                print(f"  {_status(False)} API key '{provider.api_key_env}': NOT SET")
                issues.append(f"Environment variable {provider.api_key_env} is not set")
        else:
            print(f"  {_status(True)} Provider '{provider_name}': no API key needed")

    return issues


def check_models(config) -> List[str]:
    """Check each model can produce a response."""
    issues: List[str] = []

    if config is None:
        return issues

    tested_providers: Dict[str, str] = {}  # provider_name → model_id

    for key, model in config.models.items():
        if model.is_principal:
            continue

        provider_name = model.provider
        if not provider_name:
            continue

        # Only test one model per provider
        if provider_name in tested_providers:
            continue
        tested_providers[provider_name] = key

        provider = config.providers.get(provider_name)
        if not provider:
            continue

        api_key = None
        if provider.api_key_env:
            api_key = os.environ.get(provider.api_key_env)
        elif provider.api_key:
            api_key = provider.api_key

        try:
            url = provider.base_url.rstrip("/") + "/chat/completions"
            body = json.dumps({
                "model": model.model,
                "messages": [{"role": "user", "content": "Say 'OK' and nothing else."}],
                "max_tokens": 10,
                "temperature": 0,
            }).encode()

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            t0 = time.time()
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"].get("content", "")
                elapsed = time.time() - t0
                print(f"  {_status(True)} Model '{key}' ({model.model}): OK ({elapsed:.1f}s)")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            print(f"  {_status(False)} Model '{key}' ({model.model}): HTTP {e.code} — {body}")
            issues.append(f"Model '{key}' returned HTTP {e.code}")
        except Exception as e:
            print(f"  {_status(False)} Model '{key}' ({model.model}): {e}")
            issues.append(f"Model '{key}' call failed: {e}")

    return issues


def check_workflows(config) -> List[str]:
    """Check that workflow tiers reference defined models."""
    issues: List[str] = []

    if config is None:
        return issues

    for wf_name, wf in config.workflows.items():
        missing = [t for t in wf.tiers if t != "principal" and t not in config.models]
        if missing:
            print(f"  {_status(False)} Workflow '{wf_name}': missing tiers: {missing}")
            issues.append(f"Workflow '{wf_name}' references undefined tiers: {missing}")
        else:
            print(f"  {_status(True)} Workflow '{wf_name}': {wf.tiers}")

    return issues


def cmd_doctor() -> int:
    """Run all health checks. Returns 0 if healthy, 1 if issues found."""
    print("MR-Krabs Doctor")
    print("=" * 60)

    # 1. Load config
    print("\n[1/5] Config")
    config, errors = _load_config_safe()
    if errors:
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    check_config_file(config)

    # 2. API keys
    print("\n[2/5] API Keys")
    errors.extend(check_api_keys(config))

    # 3. Providers
    print("\n[3/5] Providers")
    errors.extend(check_providers(config))

    # 4. Models
    print("\n[4/5] Models")
    errors.extend(check_models(config))

    # 5. Workflows
    print("\n[5/5] Workflows")
    errors.extend(check_workflows(config))

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"✗ {len(errors)} issue(s) found:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("✓ All checks passed. MR-Krabs is ready.")
        return 0


# CLI entry point
if __name__ == "__main__":
    sys.exit(cmd_doctor())
