#!/usr/bin/env python3
"""Model ID validation against OpenRouter API."""

import os
import sys
import requests
from typing import Dict, List, Set, Tuple
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.orchestrator import MODELS


class ModelValidator:
    """Validates model IDs against OpenRouter API."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self._available_models: Set[str] = set()
        self._fetched = False
    
    def fetch_available_models(self) -> bool:
        """Fetch available models from OpenRouter."""
        if not self.api_key:
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self._available_models = {m['id'] for m in data.get('data', [])}
                self._fetched = True
                return True
            return False
        except Exception:
            return False
    
    def validate_model(self, tier: str) -> Tuple[bool, str, List[str]]:
        """
        Validate a single model ID.
        
        Returns:
            Tuple of (is_valid, message, similar_models)
        """
        config = MODELS.get(tier)
        if not config:
            return False, f"Unknown tier: {tier}", []
        
        model_id = config.get('model', '')
        provider = config.get('provider', '')
        
        # Skip non-OpenRouter models
        if provider != 'openrouter':
            return True, f"Local model ({provider}) - not validated", []
        
        # Fetch models if not already done
        if not self._fetched:
            if not self.fetch_available_models():
                return False, "Failed to fetch available models", []
        
        # Check if model exists
        if model_id in self._available_models:
            return True, "Valid", []
        
        # Find similar models (for typo detection)
        model_name = model_id.split('/')[-1]
        similar = [
            m for m in self._available_models
            if model_name in m.split('/')[-1] and m != model_id
        ][:3]
        
        message = f"Model not found: {model_id}"
        if similar:
            message += f" (Did you mean: {', '.join(similar)})"
        
        return False, message, similar
    
    def validate_all(self) -> Dict[str, Dict]:
        """Validate all configured models."""
        results = {"valid": [], "invalid": [], "local": []}
        
        for tier in MODELS.keys():
            config = MODELS[tier]
            provider = config.get('provider', '')
            
            if provider != 'openrouter':
                results["local"].append(tier)
                continue
            
            is_valid, message, similar = self.validate_model(tier)
            result = {"tier": tier, "model": config.get('model'), "message": message, "similar": similar}
            
            if is_valid:
                results["valid"].append(result)
            else:
                results["invalid"].append(result)
        
        return results
    
    def print_report(self, results: Dict[str, Dict]) -> None:
        """Print validation report."""
        print("=" * 60)
        print("MODEL VALIDATION REPORT")
        print("=" * 60)
        
        for r in results.get("valid", []):
            print(f"✓ {r['tier']}: {r['model']}")
        
        for r in results.get("local", []):
            print(f"○ {r}: {MODELS[r].get('model')} (local)")
        
        for r in results.get("invalid", []):
            print(f"✗ {r['tier']}: {r['model']}")
            if r.get('similar'):
                print(f"  Did you mean: {', '.join(r['similar'])}")
        
        print("=" * 60)
        print(f"Valid: {len(results['valid'])}, Invalid: {len(results['invalid'])}, Local: {len(results['local'])}")
        
        if results["invalid"]:
            print("\n❌ VALIDATION FAILED - Fix invalid models before proceeding")
            return False
        else:
            print("\n✓ VALIDATION PASSED")
            return True


def main():
    """CLI entry point."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable not set")
        sys.exit(1)
    
    validator = ModelValidator()
    results = validator.validate_all()
    success = validator.print_report(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
