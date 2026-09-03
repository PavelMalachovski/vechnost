"""What must never reach a log line or a Sentry breadcrumb.

The database URL was written with its password on every start; a /start
argument was logged verbatim, and one kind of argument is a gift
certificate code, which is lifetime access to whoever reads the log; and
Sentry received every INFO line as a breadcrumb plus the user's handle,
so a third party held ids, usernames and codes it had no need of.
"""

import logging
from unittest.mock import AsyncMock, patch

from vechnost_bot import monitoring
from vechnost_bot.config import settings
from vechnost_bot.handlers import start_command
from vechnost_bot.models import SessionState
from vechnost_bot.payments.database import masked_url


def test_a_database_password_is_masked_for_the_log():
    # "example" in the password keeps tests/test_no_secrets.py from reading
    # this line as a leaked credential.
    url = "postgresql+asyncpg://postgres:example-pw-hunter2@postgres.railway.internal:5432/railway"
    masked = masked_url(url)
    assert "hunter2" not in masked
    assert masked == "postgresql+asyncpg://postgres:***@postgres.railway.internal:5432/railway"


def test_a_url_without_a_password_is_left_alone():
    assert masked_url("sqlite+aiosqlite:///./vechnost.db") == "sqlite+aiosqlite:///./vechnost.db"


def test_sentry_breadcrumbs_start_at_warning_and_carry_no_default_pii():
    with (
        patch.object(settings, "sentry_dsn", "https://key@sentry.example/1"),
        patch("vechnost_bot.monitoring.LoggingIntegration") as integration,
        patch("sentry_sdk.init") as init,
    ):
        monitoring.configure_sentry()

    assert integration.call_args.kwargs["level"] == logging.WARNING
    assert init.call_args.kwargs["send_default_pii"] is False


def test_the_sentry_user_is_an_id_and_nothing_else():
    with patch("vechnost_bot.monitoring.set_user") as set_user:
        monitoring.set_user_context(123, "a_real_handle")
    assert set_user.call_args.args[0] == {"id": "123"}


async def test_a_certificate_code_in_a_start_link_is_not_logged(
    mock_update, mock_context, caplog
):
    """`/start activate_VECH-…` is how a gift is redeemed. The code must
    reach the database and nothing else."""
    mock_context.args = ["activate_VECH-ABCD-EFGH"]
    caplog.set_level(logging.DEBUG)
    with (
        patch(
            "vechnost_bot.payments.services.activate_certificate",
            AsyncMock(return_value={"status": "success"}),
        ),
        patch("vechnost_bot.payments.middleware.check_and_register_user", AsyncMock()),
        patch("vechnost_bot.handlers.get_session", AsyncMock(return_value=SessionState())),
    ):
        await start_command(mock_update, mock_context)

    assert "ABCD-EFGH" not in caplog.text
    assert "activate_VECH" not in caplog.text
    # The user still got their confirmation.
    mock_update.message.reply_text.assert_awaited()
