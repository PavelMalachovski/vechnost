"""No em dashes in the content.

The card sets text at a large size on a narrow measure, where an em dash
opens a hole in the line. Where the punctuation is genuinely needed the
content uses an en dash instead; where it was standing in for a comma or a
colon, the sentence was rewritten.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONTENT = sorted(
    [ROOT / "data" / "questions.yaml"] + list((ROOT / "data" / "library").glob("*.yaml"))
)


@pytest.mark.parametrize("path", CONTENT, ids=lambda p: p.name)
def test_content_has_no_em_dash(path):
    text = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if "—" in line
    ]
    assert not offenders, "em dash left in:\n" + "\n".join(offenders)
