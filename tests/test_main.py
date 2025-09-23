"""Tests for main application entry point."""

import pytest
import sys
from unittest.mock import patch, MagicMock

from vechnost_bot.main import main


class TestMain:
    """Test main application entry point."""

    @patch('vechnost_bot.main.run_bot')
    def test_main_success(self, mock_run_bot):
        """Test successful main execution."""
        mock_run_bot.return_value = None

        # Should not raise any exceptions
        main()

        mock_run_bot.assert_called_once()

    @patch('vechnost_bot.main.run_bot')
    def test_main_exception_handling(self, mock_run_bot):
        """Test main with exception handling."""
        mock_run_bot.side_effect = Exception("Test error")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('vechnost_bot.main.run_bot')
    @patch('sys.exit')
    def test_main_keyboard_interrupt(self, mock_exit, mock_run_bot):
        """Test main with keyboard interrupt."""
        mock_run_bot.side_effect = KeyboardInterrupt()

        main()

        mock_exit.assert_called_once_with(0)

    @patch('vechnost_bot.main.run_bot')
    @patch('sys.exit')
    def test_main_general_exception(self, mock_exit, mock_run_bot):
        """Test main with general exception."""
        mock_run_bot.side_effect = Exception("Unexpected error")

        main()

        mock_exit.assert_called_once_with(1)
