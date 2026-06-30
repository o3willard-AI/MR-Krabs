"""PI Provider Mapping Layer.

Translates between MR-Krabs tier model specs (e.g. "bakeoff23/ornith-35b-q4")
and PI's provider registry (~/.pi/agent/models.json). Provides validation,
diagnostics, and server health checks to prevent silent PI failures.

Used by _execute_pi_tier() to validate models before spawning PI subprocesses.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _pi_models_path() -> Path:
    """Locate PI's models.json, respecting PI_CONFIG_PATH env var."""
    env_path = os.environ.get("PI_CONFIG_PATH", "")
    if env_path:
        return Path(env_path)
    return Path.home() / ".pi" / "agent" / "models.json"


class PIModelRegistry:
    """In-memory index of PI's provider/model registry for fast lookups."""

    def __init__(self) -> None:
        self._path = _pi_models_path()
        self._data: dict[str, Any] = {}
        self._model_index: dict[str, dict[str, Any]] = {}  # "provider/model_id" → model_info
        self._providers: dict[str, dict[str, Any]] = {}    # provider_name → provider_info
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load PI's models.json on first access."""
        if self._loaded:
            return
        try:
            raw = self._path.read_text()
            self._data = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}
        self._index()
        self._loaded = True

    def reload(self) -> None:
        """Force re-read of PI's models.json (e.g. after config change)."""
        self._loaded = False
        self._model_index.clear()
        self._providers.clear()
        self._ensure_loaded()

    def _index(self) -> None:
        """Build provider and model indices from raw JSON."""
        providers = self._data.get("providers", {})
        for prov_name, prov_info in providers.items():
            if not isinstance(prov_info, dict):
                continue
            self._providers[prov_name] = {
                "base_url": prov_info.get("baseUrl", prov_info.get("base_url", "")),
                "api": prov_info.get("api", ""),
                "api_key_set": bool(
                    prov_info.get("apiKey")
                    or prov_info.get("api_key")
                    or os.environ.get(prov_info.get("apiKeyEnv", ""))
                ),
            }
            for model in prov_info.get("models", []):
                model_id = model.get("id", "")
                full_key = f"{prov_name}/{model_id}"
                self._model_index[full_key] = {
                    "provider": prov_name,
                    "model_id": model_id,
                    "name": model.get("name", model_id),
                    "context_window": model.get("contextWindow", model.get("context_window", 0)),
                    "reasoning": model.get("reasoning", False),
                }

    def resolve(self, model_spec: str) -> dict[str, Any] | None:
        """Resolve a PI model spec (e.g. 'bakeoff23/ornith-35b-q4').

        Returns model info dict with provider details, or None if not found.
        """
        self._ensure_loaded()
        return self._model_index.get(model_spec)

    def get_provider(self, provider_name: str) -> dict[str, Any] | None:
        """Get provider info (base_url, api, api_key_set)."""
        self._ensure_loaded()
        return self._providers.get(provider_name)

    def list_models(self) -> list[str]:
        """Return all known model specs sorted alphabetically."""
        self._ensure_loaded()
        return sorted(self._model_index.keys())

    def suggest_fix(self, model_spec: str) -> str | None:
        """Suggest the closest matching model if the given spec isn't found."""
        self._ensure_loaded()
        if model_spec in self._model_index:
            return None

        # Try partial matches: same model_id across providers
        parts = model_spec.split("/", 1)
        if len(parts) == 2:
            suffix = parts[1]
            candidates = [
                k for k in self._model_index
                if k.endswith(f"/{suffix}")
            ]
            if candidates:
                return f"Model '{model_spec}' not found. Did you mean one of: {', '.join(candidates)}?"

        # Generic fallback
        available = self.list_models()
        if available:
            sample = ", ".join(available[:5])
            return (
                f"Model '{model_spec}' not found in PI registry ({self._path}).\n"
                f"Available models ({len(available)}): {sample}"
                f"{'...' if len(available) > 5 else ''}"
            )
        return f"Model '{model_spec}' not found. PI registry is empty or missing ({self._path})."

    def check_server_health(self, provider_name: str) -> tuple[bool, str]:
        """Check if a provider's server is reachable via HTTP HEAD.

        Returns (reachable: bool, message: str).
        """
        import urllib.request
        self._ensure_loaded()
        info = self._providers.get(provider_name)
        if not info:
            return False, f"Provider '{provider_name}' not in PI registry"

        base_url = info.get("base_url", "")
        if not base_url:
            return False, f"Provider '{provider_name}' has no base_url"

        # Try /v1/models endpoint (OpenAI-compatible)
        url = base_url.rstrip("/") + "/v1/models"
        try:
            req = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(req, timeout=5)
            return True, f"Server reachable at {url}"
        except urllib.error.HTTPError as e:
            # 4xx/5xx but server is there — try GET for better message
            try:
                req = urllib.request.Request(url, method="GET")
                urllib.request.urlopen(req, timeout=5)
                return True, f"Server reachable at {url} (HEAD returned {e.code})"
            except Exception:
                return True, f"Server reachable at {url} (HEAD returned {e.code})"
        except Exception as e:
            return False, f"Cannot reach {url}: {e}"


# Singleton for module-level access
_registry: PIModelRegistry | None = None


def get_registry() -> PIModelRegistry:
    """Get or create the singleton PI model registry."""
    global _registry
    if _registry is None:
        _registry = PIModelRegistry()
    return _registry


def resolve_pi_model(model_spec: str) -> dict[str, Any] | None:
    """Convenience: resolve a model spec through the singleton registry."""
    return get_registry().resolve(model_spec)


def validate_or_diagnose(model_spec: str) -> tuple[bool, str]:
    """Validate a PI model spec and return diagnostic info.

    Returns (valid: bool, message: str). The message is suitable for
    logging/printing, containing the resolved model details or a suggestion.
    """
    reg = get_registry()
    info = reg.resolve(model_spec)

    if info:
        provider = info["provider"]
        prov_info = reg.get_provider(provider)
        base = prov_info["base_url"] if prov_info else "?"
        api_key_ok = "✓" if (prov_info and prov_info["api_key_set"]) else "✗"
        return True, (
            f"Model '{model_spec}' → {info['name']} "
            f"(ctx={info['context_window']}, reason={info['reasoning']}, "
            f"server={base}, key={api_key_ok})"
        )

    suggestion = reg.suggest_fix(model_spec)
    return False, suggestion or f"Model '{model_spec}' not found"
