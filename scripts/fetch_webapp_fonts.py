"""Fetch the cyrillic+latin woff2 subsets of the brand fonts for the Mini App.

Google Fonts serves one @font-face per unicode-range; the Mini App needs the
cyrillic and latin blocks of each family and nothing else, which keeps the
whole typographic payload under ~120 KB.
"""

import re
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
OUT = Path(__file__).parent.parent / "webapp" / "fonts"

# family query -> output stem
WANTED = {
    "Forum": "forum-400",
    "Lora:wght@400": "lora-400",
    "Inter:wght@400": "inter-400",
    "Inter:wght@600": "inter-600",
    "Inter:wght@700": "inter-700",
}

_BLOCK = re.compile(r"unicode-range:([^;]+);", re.S)
_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
_URL = re.compile(r"url\((https://[^)]+\.woff2)\)")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        return r.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for family, stem in WANTED.items():
        css = _get(f"https://fonts.googleapis.com/css2?family={family}").decode()
        for face in _FACE.findall(css):
            ranges = _BLOCK.search(face)
            url = _URL.search(face)
            if not ranges or not url:
                continue
            text = ranges.group(1)
            if "U+0301" in text or "U+0400" in text:
                suffix = ""          # cyrillic block -> the primary file
            elif text.strip().startswith("U+0000"):
                suffix = "-latin"    # basic latin block
            else:
                continue
            path = OUT / f"{stem}{suffix}.woff2"
            path.write_bytes(_get(url.group(1)))
            print(f"{path.name}  {path.stat().st_size} B")


if __name__ == "__main__":
    main()
