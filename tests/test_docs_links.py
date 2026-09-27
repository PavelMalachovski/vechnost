"""The documents we keep true link only to things that exist.

Legacy notes moved to docs/archive/, and files the documents used to point
at were deleted; a link that 404s on GitHub is the first sign a document has
drifted from the code. The audit report is left out on purpose: it records
the state of the tree when each finding was written.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
KEPT = [
    "README.md",
    "CLAUDE.md",
    "docs/CI_CD.md",
    "docs/RAILWAY_DEPLOYMENT.md",
    "docs/ENVIRONMENT_VARIABLES.md",
    "docs/PAYMENT_SETUP_GUIDE.md",
    "scripts/README.md",
    "tests/e2e/README.md",
]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _anchors(markdown: str) -> set[str]:
    """GitHub's heading anchors: lower case, punctuation dropped, spaces to -."""
    return {
        re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
        for heading in re.findall(r"^#+\s+(.+)$", markdown, flags=re.M)
    }


@pytest.mark.parametrize("document", KEPT)
def test_every_relative_link_resolves(document):
    source = REPO / document
    broken = []
    for target in LINK.findall(source.read_text(encoding="utf-8")):
        if re.match(r"[a-z]+:", target):  # https:, mailto:
            continue
        path, _, anchor = target.partition("#")
        resolved = (source.parent / path).resolve() if path else source
        if not resolved.exists():
            broken.append(target)
        elif anchor and resolved.suffix == ".md" and anchor not in _anchors(
            resolved.read_text(encoding="utf-8")
        ):
            broken.append(target)
    assert not broken, f"{document} links to what is not there: {broken}"
