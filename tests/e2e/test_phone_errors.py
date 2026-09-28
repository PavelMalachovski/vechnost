"""What a phone in the browser suite counts as the app misbehaving
(tests/e2e/browser/phones.py): everything the page reports, except WebKit's
word for a request that leaving the page cancelled."""

from tests.e2e.browser.phones import cancelled_by_webkit

BASE = "http://127.0.0.1:8000"


def test_a_request_to_the_app_cancelled_by_leaving_the_page_is_not_an_error():
    """What the UI fuzzer's "closes the app and opens it again" left behind
    on an iPhone, with a /api/steps69 poll still in flight."""
    as_reported = (
        "/127.0.0.1:8000/api/steps69/ZTW7WP9A2CZ9LBS6?lang=ru due to access control checks."
    )
    assert cancelled_by_webkit(as_reported, BASE)
    assert cancelled_by_webkit(
        "Fetch API cannot load http://127.0.0.1:8000/api/rooms/X due to access control checks.",
        BASE,
    )


def test_anything_else_still_is():
    assert not cancelled_by_webkit("TypeError: undefined is not an object", BASE)
    # Another origin can fail its access control for real.
    assert not cancelled_by_webkit(
        "Fetch API cannot load https://example.org/x due to access control checks.", BASE
    )
