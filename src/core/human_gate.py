import os
import time
import json
from pathlib import Path
from typing import Tuple, Optional


def _pending_dir() -> Path:
    """Lazy compute the pending directory so tests can override HOME."""
    return Path(os.path.expanduser("~/.mrkrabs/pending"))


TIMEOUT_MINUTES = 15  # default

def write_pending_file(task_id: str, info: dict) -> Path:
    """Write {task_id}.json with current state to ~/.mrkrabs/pending/"""
    pending_dir = _pending_dir()
    pending_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = pending_dir / f"{task_id}.json"
    with open(file_path, 'w') as f:
        json.dump(info, f, indent=2)
    
    return file_path

def wait_for_human(task_id: str, timeout_minutes: float = 15.0) -> Tuple[bool, Optional[str]]:
    """
    Poll the pending file every 2 seconds for {confirmed: true/false, reason: "..."}.
    Returns (True, None) if confirmed, (False, reason) if denied or timeout.
    """
    file_path = _pending_dir() / f"{task_id}.json"
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        # Check if the file exists
        if not file_path.exists():
            time.sleep(2)
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Check for confirmation
            if 'confirmed' in data:
                if data['confirmed']:
                    return True, None  # Confirmed
                else:
                    return False, data.get('reason', 'User denied escalation')  # Denied
            
            # If we got here, file exists but no decision yet, wait and continue polling
            time.sleep(2)
            
        except (json.JSONDecodeError, IOError):
            # File is being written or corrupted, wait and retry
            time.sleep(2)
            continue
    
    # Timeout reached
    return False, f"Timeout after {timeout_minutes} minutes waiting for human confirmation"

def confirm_task(task_id: str) -> None:
    """External call: confirm escalation for a pending task."""
    file_path = _pending_dir() / f"{task_id}.json"
    
    if file_path.exists():
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        data['confirmed'] = True
        data['confirmed_at'] = time.time()
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

def deny_task(task_id: str, reason: str = "") -> None:
    """External call: deny escalation for a pending task."""
    file_path = _pending_dir() / f"{task_id}.json"
    
    if file_path.exists():
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        data['confirmed'] = False
        data['reason'] = reason
        data['denied_at'] = time.time()
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)