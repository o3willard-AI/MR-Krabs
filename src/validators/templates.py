#!/usr/bin/env python3
"""Template file validation."""

import os
from pathlib import Path
from typing import Dict, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TemplateValidator:
    """Validates prompt template files."""
    
    REQUIRED_TEMPLATES = {
        "L0-Planner": "01-planner.md",
        "L0-Coder": "02-l0-coder.md",
        "L0-Reviewer": "03-reviewer.md",
        "L1-Coder": "04-l1-coder.md",
        "L2-Coder": "05-l2-coder.md",
        "L3-Coder": "05-l2-coder.md",
        "L3-Architect": "06-l3-architect.md"
    }
    
    def __init__(self, templates_dir: str = None):
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Default to orchestrator/templates
            self.templates_dir = Path(__file__).parent.parent.parent / "templates"
    
    def validate_template(self, filename: str) -> tuple[bool, str]:
        """Validate a single template file."""
        filepath = self.templates_dir / filename
        
        if not filepath.exists():
            return False, f"File not found: {filepath}"
        
        if not filepath.is_file():
            return False, f"Not a file: {filepath}"
        
        content = filepath.read_text()
        
        if len(content) < 50:
            return False, f"File too short ({len(content)} chars): {filename}"
        
        if "# ROLE:" not in content:
            return False, f"Missing '# ROLE:' section: {filename}"
        
        return True, f"Valid ({len(content)} chars)"
    
    def validate_all(self) -> Dict[str, Dict]:
        """Validate all required templates."""
        results = {"valid": [], "invalid": [], "missing": []}
        checked = set()
        
        for tier, filename in self.REQUIRED_TEMPLATES.items():
            if filename in checked:
                continue
            checked.add(filename)
            
            is_valid, message = self.validate_template(filename)
            result = {"tier": tier, "file": filename, "message": message}
            
            if is_valid:
                results["valid"].append(result)
            elif "not found" in message.lower():
                results["missing"].append(result)
            else:
                results["invalid"].append(result)
        
        return results
    
    def print_report(self, results: Dict) -> bool:
        """Print validation report."""
        print("=" * 60)
        print("TEMPLATE VALIDATION REPORT")
        print("=" * 60)
        print(f"Templates directory: {self.templates_dir}")
        print()
        
        for r in results.get("valid", []):
            print(f"✓ {r['file']}: {r['message']}")
        
        for r in results.get("invalid", []):
            print(f"✗ {r['file']}: {r['message']}")
        
        for r in results.get("missing", []):
            print(f"✗ {r['file']}: {r['message']}")
        
        print("=" * 60)
        print(f"Valid: {len(results['valid'])}, Invalid: {len(results['invalid'])}, Missing: {len(results['missing'])}")
        
        if results["invalid"] or results["missing"]:
            print("\n❌ VALIDATION FAILED")
            return False
        else:
            print("\n✓ ALL TEMPLATES VALID")
            return True


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Validate template files")
    parser.add_argument("--dir", help="Templates directory")
    args = parser.parse_args()
    
    validator = TemplateValidator(args.dir) if args.dir else TemplateValidator()
    results = validator.validate_all()
    success = validator.print_report(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
