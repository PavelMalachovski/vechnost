#!/usr/bin/env python
"""Send one message to every registered user.

Deliberately a script and not a bot command: a broadcast is irreversible and
reaches thousands of people, so it should take a deliberate act on a machine
someone controls, not a tap that a stray callback could ever reach.

    python scripts/broadcast.py --message-file msg.txt --dry-run
    python scripts/broadcast.py --message-file msg.txt --limit 5   # a rehearsal
    python scripts/broadcast.py --message-file msg.txt --confirm

Nothing is sent without --confirm. A user who has blocked the bot is skipped
and opted out of the daily push as well, since that is the same signal.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden, RetryAfter

from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("broadcast")

# Telegram's documented ceiling for bulk sends is about 30 messages a second.
# Well under it: a broadcast is not in a hurry, and a 429 costs more than the
# pause it would have taken to avoid one.
SECONDS_BETWEEN_SENDS = 0.06


async def _recipients() -> list[tuple[int, str | None]]:
    """Everyone the bot knows, as (telegram_user_id, first_name)."""
    async with get_db() as session:
        users = await UserRepository.get_all(session)
        return [(u.telegram_user_id, u.first_name) for u in users]


def _keyboard() -> InlineKeyboardMarkup | None:
    """The app button, so the message is also the way into what it announces."""
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть VECHNOST", web_app=WebAppInfo(url=settings.webapp_url))
    ]])


async def broadcast(text: str, confirm: bool, limit: int | None) -> int:
    recipients = await _recipients()
    if limit is not None:
        recipients = recipients[:limit]

    if not confirm:
        print("\n--- DRY RUN, nothing will be sent ---")
        print(f"Recipients: {len(recipients)}")
        print(f"Button: {'yes' if _keyboard() else 'no (WEBAPP_URL is unset)'}")
        print(f"\nMessage:\n{text}\n")
        print("Re-run with --confirm to send.")
        return 0

    bot = Bot(token=settings.telegram_bot_token)
    keyboard = _keyboard()
    sent = blocked = failed = 0

    for index, (user_id, name) in enumerate(recipients, 1):
        try:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
            sent += 1
        except RetryAfter as e:
            # Told exactly how long to wait: wait, then give this user one
            # more try rather than dropping them for being unlucky.
            logger.warning(f"Rate limited, sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
                sent += 1
            except Exception as retry_error:
                failed += 1
                logger.warning(f"{user_id} ({name}) failed after retry: {retry_error}")
        except Forbidden:
            blocked += 1
            async with get_db() as session:
                await UserRepository.set_daily_card_opt_out(session, user_id, True)
        except Exception as e:
            failed += 1
            logger.warning(f"{user_id} ({name}) failed: {e}")

        if index % 100 == 0:
            logger.info(f"{index}/{len(recipients)} processed")
        await asyncio.sleep(SECONDS_BETWEEN_SENDS)

    logger.info(f"Done: {sent} sent, {blocked} blocked the bot, {failed} failed")
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message-file", type=Path, help="UTF-8 file holding the message")
    source.add_argument("--message", help="the message itself")
    parser.add_argument("--confirm", action="store_true",
                        help="actually send. Without it this is a dry run.")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be sent and stop. The default, "
                             "but say it out loud when you mean it.")
    parser.add_argument("--limit", type=int,
                        help="send to at most N users, for a rehearsal")
    args = parser.parse_args()

    text = (
        args.message_file.read_text(encoding="utf-8").strip()
        if args.message_file else args.message
    )
    if not text:
        parser.error("the message is empty")

    if args.dry_run and args.confirm:
        parser.error("--dry-run and --confirm contradict each other")

    asyncio.run(broadcast(text, args.confirm and not args.dry_run, args.limit))


if __name__ == "__main__":
    main()
