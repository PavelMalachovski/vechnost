"""The admin broadcast: who may run it, and what a bulk send survives."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Message
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot import broadcast as bc
from vechnost_bot.config import Settings, settings


def _run(coro):
    """Drive a coroutine on a fresh loop.

    The repo's session-scoped `event_loop` fixture makes plain `async def`
    tests error out with ScopeMismatch, so the send-path tests drive the
    loop themselves rather than going uncovered.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


# ── ADMIN_IDS ────────────────────────────────────────────────────────

class TestAdminIds:
    def test_unset_means_nobody(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t"}, clear=True):
            assert Settings().admin_user_ids == frozenset()

    def test_a_comma_separated_list_is_read_as_numbers(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "ADMIN_IDS": " 111, 222 "}):
            assert Settings().admin_user_ids == frozenset({111, 222})

    def test_one_bad_entry_does_not_take_the_bot_down(self):
        """Settings are read at import, so raising here would mean no bot at
        all over one typo. The typo is dropped and the rest still work."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "ADMIN_IDS": "111,oops,222"}):
            assert Settings().admin_user_ids == frozenset({111, 222})

    def test_is_admin_follows_the_setting(self):
        with patch.object(settings, "admin_ids", "111"):
            assert bc.is_admin(111)
            assert not bc.is_admin(222)
            assert not bc.is_admin(None)


# ── Delivery ─────────────────────────────────────────────────────────

class TestDeliver:
    def test_a_plain_send_is_sent(self):
        send = AsyncMock()
        assert _run(bc.deliver(send, 1)) == bc.SENT
        send.assert_awaited_once_with(1)

    def test_a_blocked_user_is_opted_out_of_the_daily_push(self):
        """Blocking the bot is the same signal the daily card reads, so the
        broadcast stops the recurring push too rather than leaving it to
        fail every day from now on."""
        send = AsyncMock(side_effect=Forbidden("bot was blocked by the user"))
        with patch.object(bc, "_opt_out", new=AsyncMock()) as opt_out:
            assert _run(bc.deliver(send, 7)) == bc.BLOCKED
        opt_out.assert_awaited_once_with(7)
        assert send.await_count == 1  # no retries: there is nobody there

    def test_chat_not_found_counts_as_blocked(self):
        """A deleted account comes back as a BadRequest, not a Forbidden."""
        send = AsyncMock(side_effect=BadRequest("Chat not found"))
        with patch.object(bc, "_opt_out", new=AsyncMock()) as opt_out:
            assert _run(bc.deliver(send, 7)) == bc.BLOCKED
        opt_out.assert_awaited_once_with(7)

    def test_any_other_bad_request_is_a_failure_not_a_block(self):
        send = AsyncMock(side_effect=BadRequest("message text is empty"))
        with patch.object(bc, "_opt_out", new=AsyncMock()) as opt_out:
            assert _run(bc.deliver(send, 7)) == bc.FAILED
        opt_out.assert_not_awaited()

    def test_rate_limiting_waits_the_time_telegram_names_and_retries(self):
        send = AsyncMock(side_effect=[RetryAfter(3), None])
        slept = []
        with patch.object(bc.asyncio, "sleep", new=AsyncMock(side_effect=slept.append)):
            assert _run(bc.deliver(send, 7)) == bc.SENT
        assert slept == [4]  # retry_after + 1
        assert send.await_count == 2

    def test_a_network_error_is_retried_then_given_up_on(self):
        send = AsyncMock(side_effect=NetworkError("connection reset"))
        backoff = []
        with patch.object(bc.asyncio, "sleep", new=AsyncMock(side_effect=backoff.append)):
            assert _run(bc.deliver(send, 7)) == bc.FAILED
        assert send.await_count == bc.SEND_ATTEMPTS
        assert backoff == [2, 4, 6]  # backs off, rather than hammering

    def test_an_unknown_error_does_not_retry(self):
        send = AsyncMock(side_effect=RuntimeError("boom"))
        assert _run(bc.deliver(send, 7)) == bc.FAILED
        assert send.await_count == 1


# ── The run loop ─────────────────────────────────────────────────────

def _people(*ids):
    return [(i, f"name{i}") for i in ids]


class TestRun:
    def test_every_recipient_is_counted_in_its_own_column(self):
        outcomes = {1: None, 2: Forbidden("blocked"), 3: RuntimeError("boom")}

        async def send(user_id):
            error = outcomes[user_id]
            if error:
                raise error

        with patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1, 2, 3))), \
             patch.object(bc, "_opt_out", new=AsyncMock()), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            report = _run(bc.run(send))

        assert report.total == 3
        assert report.sent == 1
        assert report.blocked == 1
        assert report.failed == [3]

    def test_one_broken_recipient_never_ends_the_run(self):
        """The failure mode this guards is the worst one a broadcast has:
        the rest of the list gets nothing *and* nobody is told who did."""
        sent = []

        async def send(user_id):
            if user_id == 2:
                raise Exception("something nobody predicted")
            sent.append(user_id)

        with patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1, 2, 3))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            report = _run(bc.run(send))

        assert sent == [1, 3]
        assert report.sent == 2
        assert report.failed == [2]

    def test_limit_is_a_rehearsal_not_a_full_send(self):
        seen = []
        with patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1, 2, 3, 4))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            report = _run(bc.run(AsyncMock(side_effect=lambda i: seen.append(i)), limit=2))
        assert report.total == 2
        assert len(seen) == 2

    def test_a_failing_progress_callback_does_not_stop_the_send(self):
        with patch.object(bc, "recipients",
                          new=AsyncMock(return_value=_people(*range(bc.PROGRESS_EVERY + 5)))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            report = _run(bc.run(
                AsyncMock(),
                on_progress=AsyncMock(side_effect=Exception("edit failed")),
            ))
        assert report.sent == bc.PROGRESS_EVERY + 5


# ── The bot command ──────────────────────────────────────────────────

def _update(user_id=111, text="hello"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.chat_id = 500
    update.message.message_id = 42
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _context():
    context = MagicMock()
    context.user_data = {}
    context.bot.copy_message = AsyncMock()
    context.bot.send_message = AsyncMock()
    return context


class TestCommand:
    def test_a_non_admin_gets_silence(self):
        """Not a refusal: there is nothing to gain by confirming that the
        command exists."""
        update, context = _update(user_id=999), _context()
        with patch.object(settings, "admin_ids", "111"):
            _run(bc.broadcast_command(update, context))
        update.message.reply_text.assert_not_awaited()
        assert context.user_data == {}

    def test_an_admin_is_asked_for_the_message(self):
        update, context = _update(), _context()
        with patch.object(settings, "admin_ids", "111"):
            _run(bc.broadcast_command(update, context))
        update.message.reply_text.assert_awaited_once()
        assert context.user_data[bc._AWAITING] is True

    def test_the_next_message_becomes_the_preview(self):
        update, context = _update(), _context()
        context.user_data[bc._AWAITING] = True
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1, 2))):
            _run(bc.broadcast_message(update, context))

        # Copied, never re-typed: whatever the draft is made of survives.
        context.bot.copy_message.assert_awaited_once()
        assert context.user_data[bc._PREVIEW] == (500, 42)

    def test_an_admin_who_did_not_ask_is_not_captured(self):
        """The capture is armed by /broadcast and by nothing else, or every
        ordinary message an admin types would become a draft."""
        update, context = _update(), _context()
        with patch.object(settings, "admin_ids", "111"):
            _run(bc.broadcast_message(update, context))
        context.bot.copy_message.assert_not_awaited()
        assert bc._PREVIEW not in context.user_data

    def test_an_unreadable_recipient_list_stops_before_the_preview(self):
        """Reading the list is the first step of sending it, so a failure
        here is a failure of the whole thing. Say so before the confirm."""
        update, context = _update(), _context()
        context.user_data[bc._AWAITING] = True
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "recipients", new=AsyncMock(side_effect=Exception("db down"))):
            _run(bc.broadcast_message(update, context))
        assert bc._PREVIEW not in context.user_data
        update.message.reply_text.assert_awaited_once()

    def test_cancel_forgets_the_draft(self):
        update, context = _update(), _context()
        context.user_data[bc._AWAITING] = True
        with patch.object(settings, "admin_ids", "111"):
            _run(bc.broadcast_cancel_command(update, context))
        assert not context.user_data.get(bc._AWAITING)
        assert bc._PREVIEW not in context.user_data


def _query(data=bc.CONFIRM, accessible=True):
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    # `spec=Message` so the isinstance check in `_reply` sees what a live
    # callback carries. `accessible=False` is the other thing it can be: an
    # InaccessibleMessage, which a card older than 48 hours becomes.
    query.message = MagicMock(spec=Message) if accessible else MagicMock()
    query.message.reply_text = AsyncMock()
    return query


def _callback_update(query, user_id=111):
    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = user_id
    return update


class TestCallback:
    def test_a_non_admin_tap_sends_nothing(self):
        query = _query()
        context = _context()
        context.user_data[bc._PREVIEW] = (500, 42)
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "run", new=AsyncMock()) as run:
            _run(bc.broadcast_callback(_callback_update(query, user_id=999), context))
        run.assert_not_awaited()
        assert context.user_data[bc._PREVIEW] == (500, 42)

    def test_confirm_copies_the_draft_to_everybody(self):
        query, context = _query(), _context()
        context.user_data[bc._PREVIEW] = (500, 42)
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1, 2))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            _run(bc.broadcast_callback(_callback_update(query), context))

        assert context.bot.copy_message.await_count == 2
        assert {c.kwargs["chat_id"] for c in context.bot.copy_message.await_args_list} == {1, 2}
        for call in context.bot.copy_message.await_args_list:
            assert call.kwargs["from_chat_id"] == 500
            assert call.kwargs["message_id"] == 42
        query.message.reply_text.assert_awaited_once()

    def test_cancel_sends_nothing(self):
        query, context = _query(bc.CANCEL), _context()
        context.user_data[bc._PREVIEW] = (500, 42)
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "run", new=AsyncMock()) as run:
            _run(bc.broadcast_callback(_callback_update(query), context))
        run.assert_not_awaited()
        assert bc._PREVIEW not in context.user_data

    def test_a_preview_that_did_not_survive_a_restart_says_so(self):
        """`user_data` lives in the process. Without this the button would
        sit there doing nothing, which reads as a broadcast that silently
        did not go."""
        query, context = _query(), _context()
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "run", new=AsyncMock()) as run:
            _run(bc.broadcast_callback(_callback_update(query), context))
        run.assert_not_awaited()
        query.edit_message_text.assert_awaited_once()
        assert "/broadcast" in query.edit_message_text.await_args.args[0]

    def test_the_receipt_still_arrives_when_the_card_is_too_old_to_reply_to(self):
        """A card older than 48 hours is an InaccessibleMessage: it has an id
        and nothing else. The admin still has to be told what happened."""
        query, context = _query(accessible=False), _context()
        context.user_data[bc._PREVIEW] = (500, 42)
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            _run(bc.broadcast_callback(_callback_update(query), context))
        assert context.bot.send_message.await_args.kwargs["chat_id"] == 111

    def test_confirming_twice_sends_once(self):
        """The draft is popped, not read: a double tap on a slow send must
        not put the message out a second time."""
        query, context = _query(), _context()
        context.user_data[bc._PREVIEW] = (500, 42)
        with patch.object(settings, "admin_ids", "111"), \
             patch.object(bc, "recipients", new=AsyncMock(return_value=_people(1))), \
             patch.object(bc, "SECONDS_BETWEEN_SENDS", 0):
            _run(bc.broadcast_callback(_callback_update(query), context))
            _run(bc.broadcast_callback(_callback_update(query), context))
        assert context.bot.copy_message.await_count == 1


# ── Registration ─────────────────────────────────────────────────────

class TestRegistration:
    def test_no_admin_ids_means_the_command_does_not_exist(self):
        """A broadcast reaches everyone and cannot be recalled, so an
        unconfigured deployment must not have a door onto it at all."""
        from vechnost_bot.bot import create_application

        with patch.object(settings, "admin_ids", None):
            app = create_application()
        assert not _command_names(app) & {"broadcast", "cancel"}

    def test_admin_ids_registers_it_ahead_of_the_game_callbacks(self):
        from telegram.ext import CallbackQueryHandler

        from vechnost_bot.bot import create_application

        with patch.object(settings, "admin_ids", "111"):
            app = create_application()
        assert {"broadcast", "cancel"} <= _command_names(app)

        handlers = app.handlers[0]
        callbacks = [i for i, h in enumerate(handlers)
                     if isinstance(h, CallbackQueryHandler)]
        # The patterned admin handler first, the game's catch-all after it:
        # the other order routes `broadcast_confirm` into the callback
        # registry, which has no idea what it is.
        assert handlers[callbacks[0]].pattern is not None
        assert handlers[callbacks[-1]].pattern is None

    def test_the_send_does_not_hold_up_every_other_update(self):
        """A broadcast to thousands of people takes minutes. PTB runs a
        handler inline unless it is told not to, so without block=False the
        bot answers nobody until the send is done."""
        from telegram.ext import CallbackQueryHandler

        from vechnost_bot.bot import create_application

        with patch.object(settings, "admin_ids", "111"):
            app = create_application()
        patterned = [h for h in app.handlers[0]
                     if isinstance(h, CallbackQueryHandler) and h.pattern is not None]
        assert patterned and all(h.block is False for h in patterned)


def _command_names(app) -> set[str]:
    from telegram.ext import CommandHandler

    names = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            names |= set(handler.commands)
    return names


def test_the_report_names_the_ids_worth_a_manual_message():
    report = bc.BroadcastReport(total=3, sent=1, blocked=1, failed=[99])
    text = bc.report_text(report)
    assert "99" in text
    for value in ("3", "1"):
        assert value in text


def test_a_clean_report_carries_no_id_list():
    text = bc.report_text(bc.BroadcastReport(total=2, sent=2))
    assert "ID" not in text
