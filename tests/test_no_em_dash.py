"""No em dashes in the content.

The card sets text at a large size on a narrow measure, where an em dash
opens a hole in the line. Where the punctuation is genuinely needed the
content uses an en dash instead; where it was standing in for a comma or a
colon, the sentence was rewritten.

The en dash U+2013 is the sanctioned replacement and is deliberately absent
from BANNED below. Everything else that renders as a long horizontal stroke
is banned, so that a copy-paste from another editor cannot smuggle one back
in under a different codepoint.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONTENT = sorted(
    [ROOT / "data" / "questions.yaml"] + list((ROOT / "data" / "library").glob("*.yaml"))
)

BANNED = {
    "—": "U+2014 em dash",
    "―": "U+2015 horizontal bar",
    "−": "U+2212 minus sign",
    "⸺": "U+2E3A two-em dash",
    "⸻": "U+2E3B three-em dash",
    "﹘": "U+FE58 small em dash",
    "︱": "U+FE31 vertical em dash",
    "－": "U+FF0D fullwidth hyphen-minus",
}


@pytest.mark.parametrize("path", CONTENT, ids=lambda p: p.name)
def test_content_has_no_em_dash(path):
    text = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}:{n}: [{name}] {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        for char, name in BANNED.items()
        if char in line
    ]
    assert not offenders, "long dash left in:\n" + "\n".join(offenders)
