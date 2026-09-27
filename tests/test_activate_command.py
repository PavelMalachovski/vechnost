"""`/activate` with no code explains itself, in formatting Telegram accepts.

The usage text carries `<b>` and a `<КОД>` placeholder, and was sent with no
parse mode, so the player read the tags themselves: «<b>Активация
сертификата</b>». Switching the parse mode on alone would have been worse:
Telegram refuses the whole message over `<КОД>`, an unsupported tag.
"""

import re
from html import unescape
from unittest.mock import AsyncMock, MagicMock, patch

from vechnost_bot.handlers import activate_certificate_command
from vechnost_bot.i18n import get_text

# What Telegram's HTML parse mode accepts. Any other `<` starts a tag it
# refuses, and the whole message with it; a literal one is written `&lt;`.
TELEGRAM_TAG = re.compile(
    r"</?(b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|a|tg-emoji|code|pre"
    r"|blockquote)(\s[^<>]*)?>"
)


def test_the_usage_text_is_telegram_html():
    text = get_text("certificate.usage")
    stray = [c for c in TELEGRAM_TAG.sub("", text) if c in "<>"]
    assert not stray, "an unescaped angle bracket: Telegram reads it as a tag"
    # The player still sees the placeholder, angle brackets and all.
    assert "/activate <КОД>" in unescape(TELEGRAM_TAG.sub("", text))


async def test_activate_without_a_code_is_sent_as_html():
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = MagicMock()
    update.message = message
    update.effective_user.id = 42
    update.effective_chat.id = 42
    context = MagicMock()
    context.args = []

    with patch("vechnost_bot.handlers.set_user_context"), \
            patch("vechnost_bot.handlers.log_bot_event"):
        await activate_certificate_command(update, context)

    message.reply_text.assert_awaited_once()
    args, kwargs = message.reply_text.await_args
    assert args[0] == get_text("certificate.usage")
    assert kwargs.get("parse_mode") == "HTML"
