#!/usr/bin/env python
"""Send one message to every registered user, from a shell.

The other door onto the same delivery loop. `/broadcast` in the bot is the
convenient one, for whoever writes the announcement; this is the deliberate
one, and it is what a rehearsal and a dry run are for.

    python scripts/broadcast.py --message-file msg.txt --dry-run
    python scripts/broadcast.py --message-file msg.txt --limit 5   # a rehearsal
    python scripts/broadcast.py --message-file msg.txt --confirm

Nothing is sent without --confirm. Flood control, retries and the rule that
a user who has blocked the bot is opted out of the daily push too all live
in `vechnost_bot/broadcast.py`, so both doors behave the same way.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Bot

from vechnost_bot.broadcast import app_keyboard, recipients, run
from vechnost_bot.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("broadcast")


async def broadcast(text: str, confirm: bool, limit: int | None) -> int:
    if not confirm:
        people = await recipients()
        if limit is not None:
            people = people[:limit]
        print("\n--- DRY RUN, nothing will be sent ---")
        print(f"Recipients: {len(people)}")
        print(f"Button: {'yes' if app_keyboard() else 'no (WEBAPP_URL is unset)'}")
        print(f"\nMessage:\n{text}\n")
        print("Re-run with --confirm to send.")
        return 0

    bot = Bot(token=settings.telegram_bot_token)
    keyboard = app_keyboard()

    async def send(user_id: int) -> object:
        return await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)

    async def progress(done: int, total: int) -> None:
        logger.info(f"{done}/{total} processed")

    report = await run(send, limit=limit, on_progress=progress)
    logger.info(
        f"Done: {report.sent} sent, {report.blocked} blocked the bot, "
        f"{len(report.failed)} failed"
    )
    if report.failed:
        logger.info(f"Failed ids: {', '.join(str(i) for i in report.failed)}")
    return report.sent


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
