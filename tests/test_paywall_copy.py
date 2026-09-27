"""The paywall says the same thing in the bot and in the Mini App.

Both list what a payment opens and make the same two promises. They were
written apart, and drifted: the bot promised «сотни вопросов» and nothing
else, the app named neither the test, the board nor the masterclass. The
Mini App's `payItems` and `payPromise` (webapp/index.html) and the bot's
`payment.unlock_message` (data/translations_ru.yaml) are compared here item
by item, and both are held to the pitch in the `features:` block.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def _app() -> tuple[list[str], str]:
    html = (ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
    block = html.split("payItems: [", 1)[1].split("],", 1)[0]
    items = re.findall(r"'([^']*)'", block)
    promise = re.search(r"payPromise: '([^']*)'", html)
    assert promise, "payPromise is gone from the Mini App's I18N"
    return items, promise.group(1)


def _bot() -> dict:
    return yaml.safe_load((ROOT / "data" / "translations_ru.yaml").read_text(encoding="utf-8"))


def test_the_bot_and_the_app_list_the_same_things() -> None:
    items, promise = _app()
    message = _bot()["payment"]["unlock_message"]
    bullets = [line[2:] for line in message.splitlines() if line.startswith("• ")]
    assert bullets == items
    assert message.rstrip().endswith(promise)


def test_the_list_names_every_paid_feature_of_the_pitch() -> None:
    """The pitch (`features:`) is what VECHNOST contains; everything in it is
    paid, so the paywall has to name each one."""
    items, _ = _app()
    listed = " ".join(items).lower()
    for key, words in {
        "steps69_title": "«69 ступеней»",
        "guide_title": "мастер-класс",
        "compat_title": "тест совместимости",
        "library_title": "практики",
    }.items():
        assert key in _bot()["features"], key
        assert words in listed, f"the paywall does not name {key}"
    assert "4 колоды" in listed


def test_the_promise_says_the_partner_does_not_pay() -> None:
    _, promise = _app()
    assert "навсегда" in promise
    assert "партнёру платить не нужно" in promise
