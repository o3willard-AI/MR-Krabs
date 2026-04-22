#!/usr/bin/env python3
"""Startup validation - runs all validators before execution."""

import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validators.models import ModelValidator
from src.validators.api_keys import APIKeyValidator
from src.validators.templates import TemplateValidator


class StartupValidator:
    """Runs all startup validations."""
    
    def __init__(self, templates_dir: str = None):
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.model_validator = ModelValidator(self.api_key)
        self.api_key_validator = APIKeyValidator()
        self.template_validator = TemplateValidator(templates_dir)
    
    def validate_all(self) -> tuple[bool, Dict]:
        """
        Run all validations.
        
        Returns:
            Tuple of (all_passed, results_dict)
        """
        results = {
            "api_keys": self.api_key_validator.validate_all(),
            "models": self.model_validator.validate_all(),
            "templates": self.template_validator.validate_all()
        }
        
        all_passed = (
            len(results["api_keys"]["invalid"]) == 0 and
            len(results["models"]["invalid"]) == 0 and
            len(results["templates"]["invalid"]) == 0 and
            len(results["templates"]["missing"]) == 0
        )
        
        return all_passed, results
    
    def print_report(self, results: Dict) -> bool:
        """Print comprehensive validation report."""
        print("\n" + "=" * 70)
        print(" " * 20 + "STARTUP VALIDATION REPORT")
        print("=" * 70)
        
        # API Keys
        print("\n[1/3] API KEYS")
        print("-" * 70)
        api_passed = self.api_key_validator.print_report(results["api_keys"])
        
        # Models
        print("\n[2/3] MODELS")
        print("-" * 70)
        model_passed = self.model_validator.print_report(results["models"])
        
        # Templates
        print("\n[3/3] TEMPLATES")
        print("-" * 70)
        template_passed = self.template_validator.print_report(results["templates"])
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        checks = [
            ("API Keys", api_passed),
            ("Models", model_passed),
            ("Templates", template_passed)
        ]
        
        all_passed = True
        for name, passed in checks:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {name}: {status}")
            if not passed:
                all_passed = False
        
        print("=" * 70)
        
        if all_passed:
            print("\n✓ ALL VALIDATIONS PASSED - Ready to execute tasks\n")
        else:
            print("\n❌ VALIDATIONS FAILED - Fix issues before proceeding\n")
        
        return all_passed


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Run startup validation")
    parser.add_argument("--templates-dir", help="Templates directory")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    args = parser.parse_args()
    
    validator = StartupValidator(args.templates_dir)
    all_passed, results = validator.validate_all()
    
    if not args.quiet:
        success = validator.print_report(results)
    else:
        success = all_passed
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
