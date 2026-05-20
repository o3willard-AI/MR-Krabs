#!/usr/bin/env python3

import tempfile
from pathlib import Path
import os
import json
from unittest.mock import patch

# Let's debug exactly what happens in the function by copying it and testing step-by-step
def debug_check_mesh_fail_now():
    """Debug version of check_mesh_fail_now."""
    print("=== DEBUGGING check_mesh_fail_now ===")
    
    # This is the actual function logic, but with debugging
    signal_file = Path(os.path.expanduser("~/.mrkrabs/fail_now_signal.json"))
    print(f"Looking for signal file at: {signal_file}")
    print(f"Signal file exists: {signal_file.exists()}")
    
    if signal_file.exists():
        try:
            print("Reading file content...")
            data = json.loads(signal_file.read_text())
            print(f"File content parsed as JSON: {data}")
            tier = data.get("tier")
            print(f"Tier extracted from data: {tier}")
            
            if tier:
                print("Tier found, would set fail_now and return it")
                # Note: we won't actually call set_fail_now here for debugging
                return tier
            else:
                print("No tier found in JSON")
        except Exception as e:
            print(f"Error reading/parsing file: {e}")
    else:
        print("Signal file does not exist")

if __name__ == "__main__":
    # Test 1: No file exists (should return None)
    print("=== Test 1: No file ===")
    debug_check_mesh_fail_now()
    
    # Test 2: File exists with content
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up the home directory structure  
        fake_home = Path(tmpdir)
        mrkrabs_dir = fake_home / '.mrkrabs'
        mrkrabs_dir.mkdir(parents=True, exist_ok=True)
        
        signal_file = mrkrabs_dir / 'fail_now_signal.json'
        signal_file.write_text('{"tier": "L3-Architect"}')
        
        print(f"\n=== Test 2: File exists ===")
        print(f"Created file at: {signal_file}")
        print(f"File content: {signal_file.read_text()}")
        
        # Mock the expanduser
        with patch('src.core.fail_now.os.path.expanduser') as mock_expanduser:
            mock_expanduser.return_value = str(fake_home)
            
            print(f"Mocked home to: {fake_home}")
            debug_check_mesh_fail_now()