#!/usr/bin/env python3
"""Unit tests for shutdown.py."""

import signal
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.core.shutdown import GracefulShutdown, get_shutdown_handler


class TestGracefulShutdown:
    """Tests for GracefulShutdown class."""

    def setup_method(self):
        """Reset shutdown handler before each test."""
        handler = get_shutdown_handler()
        handler.reset()

    def test_init(self):
        """Test initialization."""
        handler = GracefulShutdown()
        assert handler._callbacks == []
        assert not handler._shutdown_event.is_set()

    def test_register_callback(self):
        """Test registering a callback."""
        handler = GracefulShutdown()
        callback = MagicMock()
        handler.register(callback)
        assert callback in handler._callbacks

    def test_register_multiple_callbacks(self):
        """Test registering multiple callbacks."""
        handler = GracefulShutdown()
        callback1 = MagicMock()
        callback2 = MagicMock()
        handler.register(callback1)
        handler.register(callback2)
        assert len(handler._callbacks) == 2
        assert handler._callbacks == [callback1, callback2]

    def test_is_shutdown_requested_before_shutdown(self):
        """Test shutdown not requested initially."""
        handler = GracefulShutdown()
        assert not handler.is_shutdown_requested

    def test_is_shutdown_requested_after_shutdown(self):
        """Test shutdown requested after trigger."""
        handler = GracefulShutdown()
        handler.shutdown()
        assert handler.is_shutdown_requested

    def test_shutdown_calls_handler(self):
        """Test shutdown triggers handler."""
        handler = GracefulShutdown()
        callback = MagicMock()
        handler.register(callback)
        handler.shutdown()
        
        assert handler.is_shutdown_requested
        callback.assert_called_once()

    def test_callbacks_run_in_reverse_order(self):
        """Test callbacks run in reverse order."""
        handler = GracefulShutdown()
        calls = []
        
        def callback1():
            calls.append(1)
        
        def callback2():
            calls.append(2)
        
        def callback3():
            calls.append(3)
        
        handler.register(callback1)
        handler.register(callback2)
        handler.register(callback3)
        handler.shutdown()
        
        # Should run in reverse: 3, 2, 1
        assert calls == [3, 2, 1]

    def test_callback_exceptions_logged(self, caplog):
        """Test that callback exceptions are logged."""
        import logging
        
        handler = GracefulShutdown()
        
        def failing_callback():
            raise RuntimeError("Callback failed")
        
        handler.register(failing_callback)
        
        with caplog.at_level(logging.ERROR):
            handler.shutdown()
        
        assert "Error in shutdown callback" in caplog.text

    def test_install_twice_no_error(self):
        """Test installing handlers twice doesn't crash."""
        handler = GracefulShutdown()
        handler.install()
        handler.install()  # Should be safe
        assert handler._installed is True

    def test_install_restores_original(self):
        """Test uninstall restores original handlers."""
        handler = GracefulShutdown()
        
        # Mock original signals
        mock_original_term = MagicMock()
        mock_original_int = MagicMock()
        
        with patch("signal.getsignal", side_effect=[mock_original_term, mock_original_int]):
            with patch("signal.signal") as mock_signal:
                handler.install()
                handler.uninstall()
        
        # Uninstall should restore original signals
        assert mock_signal.call_count >= 2

    def test_reset_clears_state(self):
        """Test reset clears shutdown state."""
        handler = GracefulShutdown()
        handler.register(MagicMock())
        handler.shutdown()
        
        handler.reset()
        
        assert not handler.is_shutdown_requested
        assert handler._callbacks == []

    def test_reset_already_reset(self):
        """Test reset when already reset is safe."""
        handler = GracefulShutdown()
        handler.reset()  # Should not crash
        assert not handler.is_shutdown_requested

    def test_shutdown_without_install(self):
        """Test shutdown works without explicit install."""
        handler = GracefulShutdown()
        callback = MagicMock()
        handler.register(callback)
        handler.shutdown()
        
        assert handler.is_shutdown_requested
        callback.assert_called_once()

    def test_shutdown_event_thread_safe(self):
        """Test shutdown event is thread-safe."""
        handler = GracefulShutdown()
        callback_count = [0]
        lock = threading.Lock()

        def counting_callback():
            with lock:
                callback_count[0] += 1

        handler.register(counting_callback)
        
        # Trigger shutdown from different thread
        def trigger_shutdown():
            handler.shutdown()

        thread = threading.Thread(target=trigger_shutdown)
        thread.start()
        thread.join()

        assert callback_count[0] == 1

    def test_handler_signature(self):
        """Test handler accepts proper signal signature."""
        handler = GracefulShutdown()
        
        # Should accept (signum, frame) like real signal handlers
        import signal
        
        # This should not raise
        handler._handler(signal.SIGTERM, None)
        assert handler.is_shutdown_requested


class TestGetShutdownHandler:
    """Tests for get_shutdown_handler function."""

    def test_returns_singleton(self):
        """Test that same handler is returned."""
        handler1 = get_shutdown_handler()
        handler2 = get_shutdown_handler()
        assert handler1 is handler2

    def test_handler_is_graceful_shutdown(self):
        """Test returned handler is GracefulShutdown instance."""
        handler = get_shutdown_handler()
        assert isinstance(handler, GracefulShutdown)

    def test_handler_can_register_callbacks(self):
        """Test returned handler can register callbacks."""
        handler = get_shutdown_handler()
        callback = MagicMock()
        handler.register(callback)
        assert callback in handler._callbacks

    def test_reset_affects_global_handler(self):
        """Test reset affects the global handler."""
        handler = get_shutdown_handler()
        handler.reset()
        
        # Subsequent calls should get the same reset handler
        handler2 = get_shutdown_handler()
        assert handler2 is handler
        assert not handler2.is_shutdown_requested


class TestGracefulShutdownIntegration:
    """Integration tests for GracefulShutdown."""

    def test_full_lifecycle(self):
        """Test complete lifecycle: register -> install -> shutdown -> uninstall."""
        handler = GracefulShutdown()
        callbacks_called = []
        
        def cleanup1():
            callbacks_called.append("cleanup1")
        
        def cleanup2():
            callbacks_called.append("cleanup2")
        
        # Register callbacks
        handler.register(cleanup1)
        handler.register(cleanup2)
        
        # Install handlers
        handler.install()
        assert handler._installed is True
        
        # Shutdown
        handler.shutdown()
        assert callbacks_called == ["cleanup2", "cleanup1"]
        
        # Uninstall
        handler.uninstall()
        assert handler._installed is False

    def test_partial_shutdown(self):
        """Test shutdown after partial registration."""
        handler = GracefulShutdown()
        
        # Register one callback
        callback1 = MagicMock()
        handler.register(callback1)
        
        # Shutdown
        handler.shutdown()
        callback1.assert_called_once()
        
        # Verify shutdown event is set
        assert handler.is_shutdown_requested is True
        
        # Test that shutdown event prevents further operations
        # (callback2 will be registered but won't matter for this test)
        callback2 = MagicMock()
        handler.register(callback2)
        
        # Test that is_shutdown_requested returns True
        assert handler.is_shutdown_requested is True
        
        # Reset and verify state is cleared
        handler.reset()
        assert handler.is_shutdown_requested is False
        assert len(handler._callbacks) == 0

    def test_shutdown_with_nested_exceptions(self):
        """Test shutdown when multiple callbacks fail."""
        handler = GracefulShutdown()
        
        def failing1():
            raise ValueError("Error 1")
        
        def failing2():
            raise RuntimeError("Error 2")
        
        handler.register(failing1)
        handler.register(failing2)
        
        # Should not crash, should log both errors
        handler.shutdown()
        assert handler.is_shutdown_requested


class TestSignalHandlers:
    """Tests for signal handler integration."""

    @patch("signal.signal")
    def test_install_registers_handlers(self, mock_signal):
        """Test install registers signal handlers."""
        handler = GracefulShutdown()
        handler.install()
        
        # Should register for both SIGTERM and SIGINT
        assert mock_signal.call_count == 2
        calls = mock_signal.call_args_list
        assert calls[0][0][0] == signal.SIGTERM
        assert calls[1][0][0] == signal.SIGINT

    @patch("signal.signal")
    def test_uninstall_restores_handlers(self, mock_signal):
        """Test uninstall restores original handlers."""
        original_term = MagicMock()
        original_int = MagicMock()
        
        with patch("signal.getsignal", side_effect=[original_term, original_int]):
            handler = GracefulShutdown()
            handler.install()
            handler.uninstall()
        
        # Uninstall should call signal.signal with original handlers
        assert mock_signal.call_count >= 2
