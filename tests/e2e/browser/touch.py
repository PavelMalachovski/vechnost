"""A finger on the glass, as close to a real one as each engine allows.

**Chromium (the Android phone): real touch, all of it.** Taps, swipes and
scrolls are CDP `Input.dispatchTouchEvent` - touchStart, touchMove through
intermediate points, touchEnd - which enters the browser where a finger
does: the compositor hit-tests it, decides whether the page or a scroller
gets the gesture, and scrolls natively. That is exactly what
`elementFromPoint` and a TouchEvent built in script cannot tell you: a
finger in the middle of a card once landed on the card's back face (hidden
from the eye, not from the compositor), behind which there is no scroller,
and long questions could not be scrolled at all while every check made from
script passed (CLAUDE.md, "Nothing but the front of a card may take a
touch").

**WebKit (the iPhone): real input, but not all of it is touch.** Playwright
drives WebKit's touchscreen with taps only (`page.touchscreen.tap`: WebKit's
own touch events and hit test, then the click a tap makes). It has no touch
drag for WebKit, so:

* a swipe is a real *mouse* drag - WebKit hit-tests the press and delivers
  mouse events, which the app's swipe engine handles exactly as it handles
  touches (it listens to both);
* a scroll is a real mouse *wheel* over the point a finger would rest on -
  WebKit's own scroll hit test decides what scrolls, which is the question
  the two hit-testing rules are about.

What is not real on WebKit, and cannot be with Playwright: a touch drag, the
touchmove events it would send, and everything iOS adds on top of WebKit -
UIKit's scroll views, its gesture recognisers, momentum and rubber-banding.
Playwright's WebKit is the Linux build; the iPhone's own compositor is not
in it. A test that needs a native touch scroll says so on WebKit rather
than pretending.
"""

from __future__ import annotations

from typing import Any

Point = tuple[float, float]


class Finger:
    """One finger on one phone."""

    #: How each gesture reaches the page, for logs and skip reasons.
    kind = "finger"
    #: Whether a drag is touch input the engine itself hit-tests and scrolls.
    touch_drag = False

    def __init__(self, page: Any) -> None:
        self.page = page

    def tap(self, x: float, y: float) -> None:
        raise NotImplementedError

    def drag(self, start: Point, end: Point, *, steps: int = 12, step_ms: int = 16) -> None:
        """A swipe from `start` to `end`."""
        raise NotImplementedError

    def scroll(self, x: float, y: float, dy: float) -> None:
        """Scroll whatever is under (x, y) by `dy` CSS pixels (down is positive)."""
        raise NotImplementedError

    @staticmethod
    def _along(start: Point, end: Point, steps: int) -> list[Point]:
        (x0, y0), (x1, y1) = start, end
        return [(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
                for i in range(1, steps + 1)]


class CdpFinger(Finger):
    """Chromium: touch input through CDP, hit-tested by the compositor."""

    kind = "CDP touch (Input.dispatchTouchEvent)"
    touch_drag = True

    def __init__(self, page: Any, context: Any) -> None:
        super().__init__(page)
        self.cdp = context.new_cdp_session(page)

    def _send(self, kind: str, points: list[Point]) -> None:
        self.cdp.send("Input.dispatchTouchEvent", {
            "type": kind,
            "touchPoints": [{"x": x, "y": y, "radiusX": 11, "radiusY": 11, "force": 0.5}
                            for x, y in points],
        })

    def tap(self, x: float, y: float) -> None:
        self._send("touchStart", [(x, y)])
        self.page.wait_for_timeout(40)
        self._send("touchEnd", [])

    def drag(self, start: Point, end: Point, *, steps: int = 12, step_ms: int = 16) -> None:
        self._send("touchStart", [start])
        for point in self._along(start, end, steps):
            self.page.wait_for_timeout(step_ms)
            self._send("touchMove", [point])
        self.page.wait_for_timeout(step_ms)
        self._send("touchEnd", [])

    def scroll(self, x: float, y: float, dy: float) -> None:
        # A finger moving up pushes the content up: the page scrolls down.
        # Slowly enough that the fling at the end adds little.
        self.drag((x, y + dy / 2), (x, y - dy / 2), steps=16, step_ms=24)


class WebKitFinger(Finger):
    """WebKit: touchscreen taps; a mouse drag for a swipe, a wheel for a scroll."""

    kind = "WebKit touchscreen tap, mouse drag, mouse wheel"
    touch_drag = False

    def tap(self, x: float, y: float) -> None:
        self.page.touchscreen.tap(x, y)

    def drag(self, start: Point, end: Point, *, steps: int = 12, step_ms: int = 16) -> None:
        mouse = self.page.mouse
        mouse.move(*start)
        mouse.down()
        for x, y in self._along(start, end, steps):
            self.page.wait_for_timeout(step_ms)
            mouse.move(x, y)
        self.page.wait_for_timeout(step_ms)
        mouse.up()

    def scroll(self, x: float, y: float, dy: float) -> None:
        self.page.mouse.move(x, y)
        self.page.mouse.wheel(0, dy)


def finger_for(page: Any, context: Any, engine: str) -> Finger:
    if engine == "chromium":
        return CdpFinger(page, context)
    return WebKitFinger(page)
