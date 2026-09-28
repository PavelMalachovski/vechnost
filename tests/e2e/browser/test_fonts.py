"""The web fonts arrive once each, on both phones (audit D-41).

A face is one file now, preloaded from <head>. A preload that the font's own
request cannot reuse - another URL, or no crossorigin, since a font is always
fetched in CORS mode - downloads the same file a second time and says so only
in the console, and a face split in two again is two requests where one
would do. So the requests are counted, from the page's own resource timing.
"""

from __future__ import annotations

from collections import Counter

from ..harness import Server
from .app import wait_home

FILES = ["inter-400.woff2", "inter-600.woff2", "inter-700.woff2", "lora-400.woff2"]
FACES = ["Inter 400", "Inter 600", "Inter 700", "Lora 400"]


def test_each_face_is_one_file_fetched_once(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    wait_home(phone)
    phone.page.wait_for_function("() => document.fonts.status === 'loaded'")
    fetched = Counter(
        phone.page.evaluate(
            """() => performance.getEntriesByType('resource')
                .map(e => e.name.split('?')[0])
                .filter(name => name.endsWith('.woff2'))
                .map(name => name.split('/').pop())"""
        )
    )
    assert fetched == Counter(FILES), fetched
    # Every face is set on the first screen, which is why all four are
    # preloaded rather than found by the stylesheet later.
    loaded = phone.page.evaluate(
        """() => [...document.fonts].filter(f => f.status === 'loaded')
            .map(f => f.family.replace(/["']/g, '') + ' ' + f.weight)"""
    )
    assert sorted(loaded) == FACES, loaded
