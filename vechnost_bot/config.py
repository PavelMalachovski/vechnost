"""Configuration management for the bot."""

import os

from telegram import Bot


def get_bot_token() -> str:
    """Get the Telegram bot token from environment variables."""
    # Support both old and new environment variable names
    token = os.getenv("API_TOKEN_TELEGRAM") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("API_TOKEN_TELEGRAM or TELEGRAM_BOT_TOKEN environment variable is required")
    return token


def get_log_level() -> str:
    """Get the log level from environment variables."""
    return os.getenv("LOG_LEVEL", "INFO").upper()


def get_chat_id() -> str | None:
    """Get the chat ID from environment variables (optional)."""
    return os.getenv("CHAT_ID")


def create_bot() -> Bot:
    """Create a Telegram bot instance."""
    token = get_bot_token()
    return Bot(token=token)
