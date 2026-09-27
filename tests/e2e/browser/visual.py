"""Visual changes: the screen tour of a pull request against the tour of master.

Committed reference pictures of a web page break whenever the browser, its
fonts or the machine's rasteriser move - the same reason CLAUDE.md warns
that `card_back.png` regenerates differently on another machine. So there
are none. `.github/workflows/visual.yml` takes both pictures in the same
job, on the same runner and the same browser build: the tour of the pull
request's merge base with master, and the tour of the pull request. Nothing
but the change itself can then differ, and the comparison can afford to be
strict:

* each picture is compared pixel by pixel on a lightly blurred difference
  of luminance, so a faint speck of anti-aliasing does not count, and
  anything a person could see does;
* a screen has changed when more than `TOLERANCE` of its pixels moved by
  more than `THRESHOLD` - a speck: a full stop added to a 15 px line moves
  twelve - or its size changed, or it exists on one side only. Two tours of
  the same code in one job come out identical to the pixel, so there is no
  noise for a larger allowance to absorb;
* content that is random by design - invite codes, the order of a room's
  deck, the dice - is masked in both tours (`screens.VISUAL_MASKS`).

`python -m tests.e2e.browser.visual BASE HEAD OUT` writes `OUT/index.html`
(base, pull request and difference side by side), `OUT/summary.md` and
`OUT/result.json`, and exits 1 when a screen changed, unless `--accept`
says the change is meant (the `visual-change` label on the pull request).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

# A pixel moved when its blurred luminance difference exceeds this (of 255),
# and a screen changed when more pixels than this moved.
THRESHOLD = 12
TOLERANCE = 4


@dataclass
class Verdict:
    """One screen at one size, compared."""

    name: str              # <phone>/<stop>@<size>.png
    status: str            # same | changed | new | gone
    moved: int = 0         # pixels that moved
    diff: str = ""         # the difference picture, relative to OUT

    @property
    def changed(self) -> bool:
        return self.status != "same"


def compare(base: Path, head: Path, out: Path) -> tuple[str, int]:
    """(status, pixels that moved); draws the difference into `out`."""
    a = Image.open(base).convert("RGB")
    b = Image.open(head).convert("RGB")
    if a.size != b.size:
        out.parent.mkdir(parents=True, exist_ok=True)
        b.save(out)
        return "changed", b.width * b.height
    delta = ImageChops.difference(a, b).convert("L").filter(ImageFilter.GaussianBlur(1))
    moved = sum(delta.histogram()[THRESHOLD + 1:])
    if moved == 0:
        return "same", 0
    # The pull request's picture, dimmed, with every moved pixel in red.
    mask = delta.point(lambda v: 255 if v > THRESHOLD else 0)
    picture = Image.blend(b, Image.new("RGB", b.size, "black"), 0.6)
    picture.paste(Image.new("RGB", b.size, (255, 32, 64)), mask=mask)
    out.parent.mkdir(parents=True, exist_ok=True)
    picture.save(out)
    return ("changed" if moved > TOLERANCE else "same"), moved


def compare_tours(base: Path, head: Path, out: Path) -> list[Verdict]:
    """Every picture of both tours (`<phone>/<stop>@<size>.png`), compared."""
    names = sorted(
        {p.relative_to(base).as_posix() for p in base.glob("*/*@*.png")}
        | {p.relative_to(head).as_posix() for p in head.glob("*/*@*.png")}
    )
    verdicts = []
    for name in names:
        if not (base / name).exists():
            verdicts.append(Verdict(name, "new"))
        elif not (head / name).exists():
            verdicts.append(Verdict(name, "gone"))
        else:
            diff = Path("diff") / name
            status, moved = compare(base / name, head / name, out / diff)
            verdicts.append(Verdict(name, status, moved, diff.as_posix() if moved else ""))
    return verdicts


def write_report(verdicts: list[Verdict], base: Path, head: Path, out: Path) -> None:
    """The report, self-contained: the pictures of every changed screen are
    copied next to it, so the artifact reads the same wherever it is opened."""
    out.mkdir(parents=True, exist_ok=True)
    changed = [v for v in verdicts if v.changed]
    for v in changed:
        for side, root in (("base", base), ("head", head)):
            if (root / v.name).exists():
                (out / side / v.name).parent.mkdir(parents=True, exist_ok=True)
                (out / side / v.name).write_bytes((root / v.name).read_bytes())
    (out / "result.json").write_text(json.dumps(
        {"threshold": THRESHOLD, "tolerance": TOLERANCE,
         "verdicts": [asdict(v) for v in verdicts]}, indent=2), encoding="utf-8")

    def img(path: str) -> str:
        if not (out / path).exists():
            return "<i>none</i>"
        return f'<a href="{html.escape(path)}"><img src="{html.escape(path)}"></a>'

    rows = "".join(
        f"<tr><th>{html.escape(v.name)}<br>{v.status} · {v.moved} px</th>"
        f"<td>{img('base/' + v.name)}</td><td>{img('head/' + v.name)}</td>"
        f"<td>{img(v.diff) if v.diff else ''}</td></tr>"
        for v in changed
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Visual changes</title><style>
body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; }}
td, th {{ vertical-align: top; padding: 6px; border-bottom: 1px solid #ddd; text-align: left; }}
img {{ width: 220px; }}
</style></head><body>
<h1>Visual changes</h1>
<p>{len(changed)} of {len(verdicts)} screens changed (a pixel counts when its blurred
luminance moved by more than {THRESHOLD}/255; a screen when more than {TOLERANCE} of
its pixels did). Columns: master, this pull request, the difference in red.</p>
<table><tr><th>Screen</th><th>master</th><th>pull request</th><th>difference</th></tr>
{rows}</table></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")

    lines = ["### Visual changes", ""]
    if not changed:
        lines.append(f"None: all {len(verdicts)} screens look as they do on master.")
    else:
        lines += [f"{len(changed)} of {len(verdicts)} screens changed:", "",
                  "| Screen | | Pixels moved |", "|---|---|---|"]
        lines += [f"| `{v.name}` | {v.status} | {v.moved or ''} |" for v in changed]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", type=Path, help="the screens folder of master's tour")
    parser.add_argument("head", type=Path, help="the screens folder of the pull request's tour")
    parser.add_argument("out", type=Path, help="where the report goes")
    parser.add_argument("--accept", action="store_true",
                        help="the change is meant: report it, do not fail")
    args = parser.parse_args(argv)
    verdicts = compare_tours(args.base, args.head, args.out)
    write_report(verdicts, args.base, args.head, args.out)
    changed = [v for v in verdicts if v.changed]
    for v in changed:
        print(f"{v.status:>8}  {v.moved:>7} px  {v.name}")
    if not verdicts:
        print("no screens to compare: did both tours run?")
        return 1
    if changed and not args.accept:
        print(f"\n{len(changed)} screen(s) look different from master. If that is the point of "
              "this pull request, add the `visual-change` label; the pictures are in the job's "
              "artifact (index.html).")
        return 1
    print(f"{len(verdicts) - len(changed)} of {len(verdicts)} screens unchanged"
          + (" (changes accepted by the visual-change label)" if changed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
