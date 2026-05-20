import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Import the modules we're testing
from src.core.notify import (
    Notifier,
    MeshNotifier,
    TelegramNotifier,
    NoopNotifier,
    FallbackNotifier
)


class TestNotifierABC(unittest.TestCase):
    """Test that the Notifier ABC can't be instantiated directly."""
    
    def test_notifier_abstract_base_cannot_be_instantiated(self):
        """Notifier ABC should not be instantiable."""
        with self.assertRaises(TypeError):
            Notifier()


class TestNoopNotifier(unittest.TestCase):
    """Test NoopNotifier functionality."""
    
    def test_noop_notifier_send_returns_true(self):
        """NoopNotifier.send() should return True."""
        notifier = NoopNotifier()
        result = notifier.send("test message")
        self.assertTrue(result)
    
    def test_noop_notifier_is_available_returns_true(self):
        """NoopNotifier.is_available() should return True."""
        notifier = NoopNotifier()
        result = notifier.is_available()
        self.assertTrue(result)


class TestMeshNotifier(unittest.TestCase):
    """Test MeshNotifier functionality."""
    
    @patch('pathlib.Path.exists')
    def test_mesh_notifier_is_available_returns_true_when_script_exists(self, mock_exists):
        """MeshNotifier.is_available() should return True when mesh_send.py exists."""
        mock_exists.return_value = True
        notifier = MeshNotifier()
        result = notifier.is_available()
        self.assertTrue(result)
    
    @patch('pathlib.Path.exists')
    def test_mesh_notifier_is_available_returns_false_when_script_missing(self, mock_exists):
        """MeshNotifier.is_available() should return False when mesh_send.py missing."""
        mock_exists.return_value = False
        notifier = MeshNotifier()
        result = notifier.is_available()
        self.assertFalse(result)
    
    @patch('pathlib.Path.exists')
    @patch('subprocess.run')
    def test_mesh_notifier_send_uses_mesh_when_available(self, mock_run, mock_exists):
        """MeshNotifier.send() should use mesh when available."""
        mock_exists.return_value = True
        mock_run.return_value.returncode = 0
        notifier = MeshNotifier()
        result = notifier.send("test message")
        self.assertTrue(result)
    
    @patch('pathlib.Path.exists')
    @patch('subprocess.run')
    def test_mesh_notifier_send_falls_back_to_file_when_mesh_fails(self, mock_run, mock_exists):
        """MeshNotifier.send() should fall back to file logging when mesh fails."""
        mock_exists.return_value = True
        mock_run.side_effect = Exception("Mesh send failed")
        with patch('src.core.notify.open', new_callable=MagicMock) as mock_open:
            notifier = MeshNotifier()
            result = notifier.send("test message")
            # Should return False (failed to send via mesh)
            self.assertFalse(result)
            # Should have attempted file logging
            mock_open.assert_called()


class TestTelegramNotifier(unittest.TestCase):
    """Test TelegramNotifier functionality."""
    
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_telegram_notifier_is_available_returns_true_when_env_set(self):
        """TelegramNotifier.is_available() should return True when env vars set."""
        notifier = TelegramNotifier()
        result = notifier.is_available()
        self.assertTrue(result)
    
    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_notifier_is_available_returns_false_when_env_missing(self):
        """TelegramNotifier.is_available() should return False when env vars missing."""
        notifier = TelegramNotifier()
        result = notifier.is_available()
        self.assertFalse(result)
    
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"})
    @patch('requests.post')
    def test_telegram_notifier_send_succeeds(self, mock_post):
        """TelegramNotifier.send() should succeed when API call works."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = TelegramNotifier()
        result = notifier.send("test message")
        self.assertTrue(result)
    
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"})
    @patch('requests.post')
    def test_telegram_notifier_send_fails_when_api_fails(self, mock_post):
        """TelegramNotifier.send() should fail when API call fails."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response
        
        notifier = TelegramNotifier()
        result = notifier.send("test message")
        self.assertFalse(result)


class TestFallbackNotifier(unittest.TestCase):
    """Test FallbackNotifier functionality."""
    
    def test_fallback_notifier_tries_first_notifier_first(self):
        """FallbackNotifier should try first notifier first."""
        # Create mock notifiers
        mock_notifier1 = MagicMock()
        mock_notifier2 = MagicMock()
        
        # Make first one available and succeed
        mock_notifier1.is_available.return_value = True
        mock_notifier1.send.return_value = True
        
        # Make second one unavailable
        mock_notifier2.is_available.return_value = False
        
        notifier = FallbackNotifier(mock_notifier1, mock_notifier2)
        result = notifier.send("test message")
        
        # Should have tried first notifier only
        mock_notifier1.send.assert_called_once()
        mock_notifier2.send.assert_not_called()
        self.assertTrue(result)
    
    def test_fallback_notifier_falls_back_to_second_when_first_unavailable(self):
        """FallbackNotifier should fall back to second notifier when first unavailable."""
        # Create mock notifiers
        mock_notifier1 = MagicMock()
        mock_notifier2 = MagicMock()
        
        # Make first one unavailable, second one available and succeed
        mock_notifier1.is_available.return_value = False
        mock_notifier2.is_available.return_value = True
        mock_notifier2.send.return_value = True
        
        notifier = FallbackNotifier(mock_notifier1, mock_notifier2)
        result = notifier.send("test message")
        
        # Should have tried second notifier only
        mock_notifier1.send.assert_not_called()
        mock_notifier2.send.assert_called_once()
        self.assertTrue(result)
    
    def test_fallback_notifier_logs_to_file_as_last_resort(self):
        """FallbackNotifier should log to file as last resort."""
        # Create mock notifiers that are both unavailable
        mock_notifier1 = MagicMock()
        mock_notifier2 = MagicMock()
        
        mock_notifier1.is_available.return_value = False
        mock_notifier2.is_available.return_value = False
        
        with patch('src.core.notify.open', new_callable=MagicMock) as mock_open:
            notifier = FallbackNotifier(mock_notifier1, mock_notifier2)
            result = notifier.send("test message")
            
            # Should return False (failed to send via any notifier)
            self.assertFalse(result)
            # Should have attempted file logging
            mock_open.assert_called()


if __name__ == '__main__':
    unittest.main()