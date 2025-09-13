"""Configuration management for the bot."""

import os

from telegram import Bot


def get_bot_token() -> str:
    """Get the Telegram bot token from environment variables."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    return token


def get_log_level() -> str:
    """Get the log level from environment variables."""
    return os.getenv("LOG_LEVEL", "INFO").upper()


def create_bot() -> Bot:
    """Create a Telegram bot instance."""
    token = get_bot_token()
    return Bot(token=token)
