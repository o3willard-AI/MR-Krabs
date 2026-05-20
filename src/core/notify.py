from abc import ABC, abstractmethod
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any


class Notifier(ABC):
    """Abstract base for notification backends."""
    
    @abstractmethod
    def send(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> bool:
        """Send a notification. Returns True on success."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this notifier is configured and reachable."""
        ...


class MeshNotifier(Notifier):
    """Send via agent mesh to primary agent.
    
    Uses mesh_send.py at ~/.hermes/scripts/mesh_send.py if available.
    Falls back to logging to ~/.mrkrabs/notifications/<timestamp>.json.
    """
    MESH_SEND_SCRIPT = os.path.expanduser("~/.hermes/scripts/mesh_send.py")
    
    def send(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> bool:
        # Try mesh send first
        if self.is_available():
            try:
                import subprocess
                result = subprocess.run(
                    [self.MESH_SEND_SCRIPT, message],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            except Exception:
                # Fall back to file log if mesh send fails
                pass
        
        # Fall back to file log
        self._log_to_file(message, urgency, context)
        return False
    
    def is_available(self) -> bool:
        return Path(self.MESH_SEND_SCRIPT).exists()
    
    def _log_to_file(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> None:
        """Log notification to file as fallback."""
        notifications_dir = Path.home() / ".mrkrabs" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.time()
        log_file = notifications_dir / f"{timestamp}.json"
        
        log_entry = {
            "timestamp": timestamp,
            "message": message,
            "urgency": urgency,
            "context": context or {}
        }
        
        with open(log_file, "w") as f:
            json.dump(log_entry, f)


class TelegramNotifier(Notifier):
    """Send via Telegram bot API.
    
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.
    """
    def send(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> bool:
        # POST to https://api.telegram.org/bot{token}/sendMessage
        try:
            import requests
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            
            if not token or not chat_id:
                return False
                
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=payload, timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def is_available(self) -> bool:
        return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


class NoopNotifier(Notifier):
    """Silent — for testing."""
    def send(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> bool:
        return True
    
    def is_available(self) -> bool:
        return True


class FallbackNotifier(Notifier):
    """Tries notifiers in order, returns True if any succeed."""
    def __init__(self, *notifiers: Notifier):
        self.notifiers = notifiers
    
    def send(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> bool:
        for n in self.notifiers:
            if n.is_available() and n.send(message, urgency, context):
                return True
        # Last resort: log to file
        self._log_to_file(message, urgency, context)
        return False
    
    def is_available(self) -> bool:
        return any(n.is_available() for n in self.notifiers)
    
    def _log_to_file(self, message: str, urgency: str = "normal", context: Optional[Dict[str, Any]] = None) -> None:
        """Log notification to file as last resort."""
        notifications_dir = Path.home() / ".mrkrabs" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.time()
        log_file = notifications_dir / f"{timestamp}.json"
        
        log_entry = {
            "timestamp": timestamp,
            "message": message,
            "urgency": urgency,
            "context": context or {}
        }
        
        with open(log_file, "w") as f:
            json.dump(log_entry, f)