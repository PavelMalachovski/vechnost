"""The shape of a Tribute webhook, and what each event means for access.

A delivery is a JSON object with the event's `name`, `created_at`,
`sent_at`, and a `payload` holding the purchase: `telegram_user_id`,
`product_id` or `subscription_id`, `amount`, `currency`, and for a
subscription its `period` and `expires_at`. Two older shapes the project's
own test scripts used (`event_name` + top-level fields, `event` + `data`)
are read as well, so a hand-made delivery still parses.

Which events change access is a table, not a substring match on the name:
the old code granted lifetime access to anything with "subscription" or
"product" in its name, cancellations included, and recorded every other
event as a payment that also counted as access. Here `new_digital_product`,
`new_subscription` and `renewed_subscription` grant; a cancellation, a
refund or a chargeback revokes; anything else is acknowledged, written
down, and changes nothing. An event Tribute adds tomorrow can only ever be
ignored, never mistaken for a purchase.

Imports nothing but pydantic, so the web layer, the scripts and the tests
share one reading of a delivery.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

Action = Literal["grant", "revoke", "ignore"]

GRANT_EVENTS = frozenset({
    "new_digital_product",
    "new_subscription",
    "renewed_subscription",
})
REVOKE_EVENTS = frozenset({
    "cancelled_subscription",
    "canceled_subscription",
    "refund",
    "refunded",
    "chargeback",
})

# A one-time purchase never expires; a subscription without a date Tribute
# vouches for is trusted for one period and no longer.
SUBSCRIPTION_FALLBACK = timedelta(days=30)


def action_for(name: str) -> Action:
    """What an event does to the buyer's access."""
    lowered = name.strip().lower()
    if lowered in GRANT_EVENTS:
        return "grant"
    if lowered in REVOKE_EVENTS:
        return "revoke"
    if any(word in lowered for word in ("refund", "chargeback", "cancel")):
        return "revoke"
    return "ignore"


def _to_int(value: Any) -> int | None:
    """An id as Tribute sends it (int, or a numeric string), or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def parse_timestamp(value: Any) -> datetime | None:
    """An ISO-8601 timestamp as a naive UTC datetime, the way the DB stores one.

    Naive on purpose: the columns are `timestamp without time zone`, and
    asyncpg refuses an aware value for one of those.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


class TributeEvent(BaseModel):
    """One delivery, read once, with every field the handler needs."""

    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
    sent_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def parse(cls, body: Any) -> "TributeEvent":
        """Read a delivery. Raises ValueError for anything that is not one."""
        if not isinstance(body, dict):
            raise ValueError("webhook body is not a JSON object")
        name = (
            body.get("name")
            or body.get("event_name")
            or body.get("event")
            or body.get("type")
            or ""
        )
        payload: dict[str, Any] = {}
        for key in ("payload", "data"):
            if isinstance(body.get(key), dict):
                payload = body[key]
                break
        try:
            sent_at = parse_timestamp(body.get("sent_at"))
            created_at = parse_timestamp(body.get("created_at"))
        except ValueError:
            sent_at = created_at = None
        return cls(
            name=str(name).strip(), payload=payload, raw=body,
            sent_at=sent_at, created_at=created_at,
        )

    @property
    def is_test(self) -> bool:
        """Tribute's connectivity ping: no event name, or an explicit flag."""
        if self.name:
            return False
        return not self.raw or any(
            self.raw.get(flag) for flag in ("test", "ping", "test_event")
        )

    @property
    def action(self) -> Action:
        return action_for(self.name)

    def _first(self, *keys: str) -> Any:
        """The first of `keys` present in the payload, the body, or a
        nested `customer` object, in that order."""
        customer = self.payload.get("customer") if isinstance(
            self.payload.get("customer"), dict
        ) else None
        raw_customer = self.raw.get("customer") if isinstance(
            self.raw.get("customer"), dict
        ) else None
        for source in (self.payload, self.raw, customer, raw_customer):
            if not source:
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
        return None

    @property
    def telegram_user_id(self) -> int | None:
        """The buyer. Raises ValueError when the payload says something
        that is not a number, so the caller can answer 400."""
        return _to_int(self._first("telegram_user_id"))

    @property
    def product_id(self) -> int | None:
        product = self.payload.get("product") if isinstance(
            self.payload.get("product"), dict
        ) else None
        value = self._first("product_id") or (product or {}).get("id")
        try:
            return _to_int(value)
        except ValueError:
            return None

    @property
    def subscription_id(self) -> int | None:
        try:
            return _to_int(self._first("subscription_id"))
        except ValueError:
            return None

    @property
    def access_key(self) -> int:
        """What the granted access is filed under: the subscription, else
        the product, else the one lifetime purchase a user can hold."""
        return self.subscription_id or self.product_id or 0

    @property
    def amount(self) -> int:
        try:
            return _to_int(self._first("amount", "price")) or 0
        except ValueError:
            return 0

    @property
    def currency(self) -> str:
        return str(self._first("currency") or "eur")

    @property
    def period(self) -> str:
        explicit = self._first("period")
        if explicit:
            return str(explicit)
        return "lifetime" if "product" in self.name.lower() else "month"

    @property
    def expires_at(self) -> datetime | None:
        """When the granted access ends. None is forever.

        A product is forever. A subscription ends when Tribute says it
        does, and when Tribute says nothing it is trusted for one period
        rather than forever: a monthly plan must not become a lifetime one
        because a field was missing.
        """
        try:
            stated = parse_timestamp(self._first("expires_at"))
        except ValueError:
            stated = None
        if stated is not None:
            return stated
        if "subscription" in self.name.lower():
            return datetime.utcnow() + SUBSCRIPTION_FALLBACK
        return None

    @property
    def username(self) -> str | None:
        value = self._first("username", "telegram_username")
        return str(value) if value else None

    @property
    def first_name(self) -> str | None:
        value = self._first("first_name")
        return str(value) if value else None

    @property
    def last_name(self) -> str | None:
        value = self._first("last_name")
        return str(value) if value else None
