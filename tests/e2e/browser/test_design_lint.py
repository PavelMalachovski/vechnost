"""The design lint over every screen, held to a baseline that can only shrink.

The screen tour (`atlas`, conftest.py) runs `design.LINT` at every stop and
size; this compares what it found with `design_baseline.json`, the findings
known today (open audit items D-11, D-12, D-14, D-25), per phone:

* a finding that is not in the baseline fails - a new small text, a new
  button under 44 px, a new colour that does not read;
* a baseline entry that no longer occurs fails too, asking for it to be
  deleted - so a fix is locked in the moment it lands, and the list can
  only get shorter.

The failure message carries the whole current list for that phone, ready
to paste over the baseline's entry once every new finding is a deliberate
one. What each finding measured (sizes, ratios, pixels) is in
`e2e-report/browser/screens/design-<phone>.json`.
"""

from __future__ import annotations

import json

import pytest

from . import design
from .phones import REPORT_DIR
from .screens import Atlas

pytestmark = [pytest.mark.browser, pytest.mark.screens]


def test_the_design_lint_finds_nothing_new_and_nothing_fixed(atlas: Atlas) -> None:
    phone = atlas.device.name
    assert not atlas.missing, (
        f"the tour stopped before {atlas.missing[0]!r}, so the lint saw only part of the app: "
        + "; ".join(atlas.errors)
    )
    found = design.findings(atlas)
    known = set(design.load_baseline().get(phone, []))
    new = sorted(set(found) - known)
    gone = sorted(known - set(found))

    report = REPORT_DIR / "screens" / f"design-{phone}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "phone": phone, "new": new, "gone": gone, "findings": found,
        "skipped_on_pictures": design.picture_notes(atlas),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {rule: sum(1 for key in found if key.startswith(rule + " |")) for rule in design.RULES}
    summary = [f"### Design lint: {phone}", "",
               "| Rule | Audit | Findings |", "|---|---|---|"]
    summary += [f"| `{rule}` | {design.AUDIT.get(rule, '')} | {counts[rule]} |" for rule in design.RULES]
    summary += ["", f"{len(new)} new, {len(gone)} fixed and still in the baseline."]
    summary += [f"- new: `{key}`: {found[key]['detail']}" for key in new]
    summary += [f"- fixed: `{key}`" for key in gone]
    (report.parent / f"design-{phone}.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    problems = []
    if new:
        problems.append(f"{len(new)} new design finding(s) on the {phone}:")
        problems += [f"  + {key}: {found[key]['detail']} at {found[key]['sizes']}" for key in new]
    if gone:
        problems.append(
            f"{len(gone)} baseline entr{'y' if len(gone) == 1 else 'ies'} no longer found on the "
            f"{phone} - fixed? Delete {'it' if len(gone) == 1 else 'them'} from design_baseline.json:"
        )
        problems += [f"  - {key}" for key in gone]
    if problems:
        problems.append(
            f"The {phone}'s list as found now (paste it over the baseline's \"{phone}\" once every "
            "new finding is deliberate):\n" + json.dumps(sorted(found), ensure_ascii=False, indent=2)
        )
    assert not problems, "\n".join(problems)
