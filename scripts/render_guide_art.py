#!/usr/bin/env python3
"""Render the masterclass's pictures from their scenes.

Each of the twenty-nine pictures of the nude masterclass is a scene in
scripts/guide_art/scenes.py - a posed person, a lamp where the card says,
props, a camera - photographed in Blender's Cycles and developed like a
low-key photograph. The pictures land in data/library/art/nude_guide/ as
WebP, where the Library API serves them under the same rules as the guide's
text: the free step to anyone, the rest to a paying reader, the poses after
the 18+ question.

The bodies are MakeHuman's (CC0), fetched on first use from a pinned wheel
on PyPI (see guide_art/makehuman.py). Rendering needs Blender as a Python
module, which is built for Python 3.11 only - a venv of its own:

    python3.11 -m venv .venv-art && .venv-art/bin/pip install -e ".[art]"
    .venv-art/bin/python scripts/render_guide_art.py

About two minutes a picture on four cores, an hour for all 29; --only
renders a few and --preview renders them small, as PNG, somewhere else.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "library" / "art" / "nude_guide"
# The picture's frame in the Mini App is 12:13.
ASPECT = 13 / 12


def render_one(key: str, size: int, samples: int, out: Path, fmt: str) -> str:
    import bpy
    import numpy as np
    from guide_art.post import develop, monochrome, to_bytes
    from guide_art.scenes import SCENES
    from guide_art.studio import shoot
    from PIL import Image

    started = time.time()
    shot = SCENES[key]()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = size, round(size * ASPECT)
    sc.cycles.samples = samples
    sc.view_settings.exposure = shot.exposure
    with tempfile.TemporaryDirectory() as tmp:
        img = shoot(Path(tmp) / "raw.png")
    seed = sum(key.encode())
    picture = develop(img, seed)
    if shot.split:
        # The editing card: as shot on the left, black and white on the right.
        half = img.shape[1] // 2
        picture = np.concatenate([picture[:, :half], monochrome(img, seed)[:, half:]], axis=1)
    image = Image.fromarray(to_bytes(picture))
    path = out / f"{key}.{fmt}"
    if fmt == "webp":
        image.save(path, "WEBP", quality=82, method=6)
    else:
        image.save(path)
    return f"{path.name}: {image.width}x{image.height} in {time.time() - started:.0f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the nude masterclass's pictures (data/library/art/nude_guide)."
    )
    parser.add_argument("--only", nargs="+", metavar="KEY", help="render just these art keys")
    parser.add_argument("--size", type=int, default=540, help="width in pixels (default 540)")
    parser.add_argument("--samples", type=int, default=192, help="Cycles samples per pixel")
    parser.add_argument("--out", type=Path, default=OUT, help="where the pictures go")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="small, quick PNGs for looking at a pose (put them somewhere with --out)",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "scripts"))
    from guide_art.scenes import SCENES

    keys = args.only or list(SCENES)
    unknown = [k for k in keys if k not in SCENES]
    if unknown:
        parser.error(f"no scene for {', '.join(unknown)}")
    size, samples, fmt = args.size, args.samples, "webp"
    if args.preview:
        size, samples, fmt = min(args.size, 270), min(args.samples, 48), "png"
    args.out.mkdir(parents=True, exist_ok=True)
    for key in keys:
        print(render_one(key, size, samples, args.out, fmt), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
