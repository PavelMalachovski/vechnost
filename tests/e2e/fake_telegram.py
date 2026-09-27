"""The Bot API, as far as VECHNOST can tell — and the two users on the other end.

The bot and the web process both talk to Telegram: the bot answers
commands, and the web process pushes «результат готов» to both partners the
moment a compatibility test completes. A fake at the HTTP layer of
python-telegram-bot (`BaseRequest`) lets the *real* handlers, keyboards and
routing run, with every outgoing call recorded per chat, so a scenario can
assert on what each partner actually received.

`BotDriver` is the other direction: it builds the updates a user's Telegram
client would send — a command, a deep link, a button press — and feeds
them to the application `bot.create_application()` builds, on the same
event loop the web app runs on, so the bot and the API share one database.
"""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from telegram import Bot, Update
from telegram.request import BaseRequest, RequestData

if TYPE_CHECKING:
    from .harness import Player, Server

BOT_ID = 5_000_000_001

# Methods that put a message in a chat, and so answer with a Message.
_SENDS = {
    "sendmessage", "sendphoto", "senddocument", "sendanimation",
    "sendvideo", "sendvoice", "sendaudio", "sendsticker",
}
_EDITS = {"editmessagetext", "editmessagecaption", "editmessagereplymarkup", "editmessagemedia"}


@dataclass
class Sent:
    """One thing the bot sent into a chat."""

    method: str
    chat_id: int
    text: str
    markup: dict[str, Any] | None
    params: dict[str, Any]

    def buttons(self) -> list[dict[str, Any]]:
        rows = (self.markup or {}).get("inline_keyboard") or []
        return [button for row in rows for button in row]


class FakeTelegram:
    """Records what the bot says, and answers the way the Bot API would."""

    def __init__(self, bot_username: str) -> None:
        self.bot_user = {
            "id": BOT_ID,
            "is_bot": True,
            "first_name": "VECHNOST",
            "username": bot_username,
            "can_join_groups": False,
            "can_read_all_group_messages": False,
            "supports_inline_queries": False,
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent: list[Sent] = []
        self.blocked: set[int] = set()
        # People who never opened a chat with the bot: Telegram refuses to
        # start one. They leave the set the moment they write to the bot.
        self.strangers: set[int] = set()
        self._ids = itertools.count(1000)

    def bot(self, token: str) -> Bot:
        return Bot(token=token, request=_FakeRequest(self), get_updates_request=_FakeRequest(self))

    def to(self, chat_id: int) -> list[Sent]:
        """Everything sent into one chat, oldest first."""
        return [sent for sent in self.sent if sent.chat_id == chat_id]

    def texts_to(self, chat_id: int) -> list[str]:
        return [sent.text for sent in self.to(chat_id)]

    def message(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        return {
            "message_id": next(self._ids),
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": self.bot_user,
            **extra,
        }

    def handle(self, method: str, params: dict[str, Any]) -> tuple[int, Any]:
        self.calls.append((method, params))
        name = method.lower()
        if name == "getme":
            return 200, self.bot_user
        chat_id = params.get("chat_id")
        if chat_id is not None and int(chat_id) in self.blocked:
            return 403, "Forbidden: bot was blocked by the user"
        if chat_id is not None and int(chat_id) in self.strangers:
            return 403, "Forbidden: bot can't initiate conversation with a user"
        if name in _SENDS or name == "copymessage":
            text = str(params.get("text") or params.get("caption") or "")
            markup = params.get("reply_markup")
            if isinstance(markup, str):
                markup = json.loads(markup)
            self.sent.append(Sent(name, int(chat_id), text, markup, params))
            if name == "copymessage":
                return 200, {"message_id": next(self._ids)}
            extra: dict[str, Any] = {}
            if params.get("text") is not None:
                extra["text"] = params["text"]
            if name == "sendphoto":
                extra["photo"] = [{
                    "file_id": "e2e-photo", "file_unique_id": "e2e", "width": 1, "height": 1,
                }]
                if params.get("caption") is not None:
                    extra["caption"] = params["caption"]
            if markup:
                extra["reply_markup"] = markup
            return 200, self.message(int(chat_id), **extra)
        if name in _EDITS:
            if params.get("inline_message_id"):
                return 200, True
            text = str(params.get("text") or params.get("caption") or "")
            markup = params.get("reply_markup")
            if isinstance(markup, str):
                markup = json.loads(markup)
            self.sent.append(Sent(name, int(chat_id), text, markup, params))
            extra = {"text": text} if text else {}
            if markup:
                extra["reply_markup"] = markup
            return 200, self.message(int(chat_id), **extra)
        # answerCallbackQuery, setMyCommands, setChatMenuButton,
        # deleteMessage, sendChatAction, ... all answer True.
        return 200, True


class _FakeRequest(BaseRequest):
    def __init__(self, telegram: FakeTelegram) -> None:
        self.telegram = telegram

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        read_timeout: Any = None,
        write_timeout: Any = None,
        connect_timeout: Any = None,
        pool_timeout: Any = None,
    ) -> tuple[int, bytes]:
        api_method = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        status, result = self.telegram.handle(api_method, params)
        if status != 200:
            body = {"ok": False, "error_code": status, "description": result}
        else:
            body = {"ok": True, "result": result}
        return status, json.dumps(body).encode()


class BotDriver:
    """Two people typing into the bot, on the web app's own event loop."""

    def __init__(self, server: Server, application: Any) -> None:
        self.server = server
        self.application = application
        self._update_ids = itertools.count(1)

    def _run(self, update: dict[str, Any]) -> None:
        sender = (update.get("message") or update.get("callback_query") or {}).get("from")
        if sender:
            # Writing to the bot opens the chat.
            self.server.telegram.strangers.discard(int(sender["id"]))
        parsed = Update.de_json(update, self.application.bot)
        self.server.portal.call(self.application.process_update, parsed)

    def _from(self, player: Player) -> dict[str, Any]:
        return {
            "id": player.id,
            "is_bot": False,
            "first_name": player.name,
            "username": player.user["username"],
            "language_code": "ru",
        }

    def send(self, player: Player, text: str) -> None:
        """The player types `text` (a command, or a /start deep link)."""
        entities = []
        if text.startswith("/"):
            entities = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        self._run({
            "update_id": next(self._update_ids),
            "message": {
                "message_id": next(self.server.telegram._ids),
                "date": int(time.time()),
                "chat": {"id": player.id, "type": "private", "first_name": player.name},
                "from": self._from(player),
                "text": text,
                "entities": entities,
            },
        })

    def press(self, player: Player, sent: Sent, callback_data: str) -> None:
        """The player taps an inline button under a message the bot sent."""
        self._run({
            "update_id": next(self._update_ids),
            "callback_query": {
                "id": str(next(self._update_ids)),
                "from": self._from(player),
                "chat_instance": f"ci-{player.id}",
                "data": callback_data,
                "message": self.server.telegram.message(
                    player.id,
                    text=sent.text or "…",
                    **({"reply_markup": sent.markup} if sent.markup else {}),
                ),
            },
        })
