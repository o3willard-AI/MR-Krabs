#!/usr/bin/env python3
"""API key validation."""

import os
from typing import Dict, List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.orchestrator import MODELS


class APIKeyValidator:
    """Validates API keys for configured providers."""
    
    def __init__(self):
        self.providers = {
            "openrouter": "OPENROUTER_API_KEY",
            "lmstudio": None,  # Local, no API key needed
        }
    
    def validate_key(self, provider: str) -> tuple[bool, str]:
        """Validate API key for a provider."""
        env_var = self.providers.get(provider)
        
        if not env_var:
            return True, f"Local provider ({provider}) - no key needed"
        
        key = os.environ.get(env_var)
        if not key:
            return False, f"Missing: {env_var}"
        
        # Basic format validation
        if len(key) < 10:
            return False, f"Invalid format: {env_var} (too short)"
        
        return True, "Valid"
    
    def validate_all(self) -> Dict[str, Dict]:
        """Validate all required API keys."""
        results = {"valid": [], "invalid": []}
        checked = set()
        
        for tier, config in MODELS.items():
            provider = config.get('provider', '')
            
            if provider in checked:
                continue
            checked.add(provider)
            
            is_valid, message = self.validate_key(provider)
            result = {"provider": provider, "message": message}
            
            if is_valid:
                results["valid"].append(result)
            else:
                results["invalid"].append(result)
        
        return results
    
    def print_report(self, results: Dict) -> bool:
        """Print validation report."""
        print("=" * 60)
        print("API KEY VALIDATION REPORT")
        print("=" * 60)
        
        for r in results.get("valid", []):
            print(f"✓ {r['provider']}: {r['message']}")
        
        for r in results.get("invalid", []):
            print(f"✗ {r['provider']}: {r['message']}")
        
        print("=" * 60)
        
        if results["invalid"]:
            print("\n❌ VALIDATION FAILED")
            print("\nTo fix:")
            for r in results["invalid"]:
                if "OPENROUTER" in r["message"]:
                    print("  export OPENROUTER_API_KEY=\"your-key-here\"")
            return False
        else:
            print("\n✓ ALL API KEYS VALID")
            return True


def main():
    """CLI entry point."""
    validator = APIKeyValidator()
    results = validator.validate_all()
    success = validator.print_report(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
