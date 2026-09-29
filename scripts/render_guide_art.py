#!/usr/bin/env python3
"""Render the masterclass's pictures from their scenes.

Each of the twenty-nine drawings of the nude masterclass is a scene in
scripts/guide_art/scenes.py - a posed figure, a lamp where the card says,
props, a camera - traced and developed like a low-key photograph. The
pictures land in data/library/art/nude_guide/ as WebP, where the Library
API serves them under the same rules as the guide's text: the free step
to anyone, the rest to a paying reader, the poses after the 18+ question.

Rendering needs numpy (pip install -e ".[art]"); the app and the tests do
not. A full run at the committed size takes a while - about a quarter of an
hour on four cores - so --only renders a few scenes and --preview renders
them small, as PNG, somewhere else.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "library" / "art" / "nude_guide"
# The drawing's frame in the Mini App is 120 by 130.
ASPECT = 13 / 12


def render_one(key: str, size: int, ss: float, out: Path, fmt: str) -> str:
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    import numpy as np
    from guide_art.post import develop, downsample, grade, monochrome, to_bytes
    from guide_art.render import render
    from guide_art.scenes import SCENES
    from PIL import Image

    started = time.time()
    shot = SCENES[key]()
    width, height = size, round(size * ASPECT)
    big = (round(width * ss), round(height * ss))
    hdr, depth = render(shot.scene, shot.cam, big[0], big[1], shot.style)
    if float(ss).is_integer():
        hdr = downsample(hdr, int(ss))
        depth = downsample(depth[..., None], int(ss))[..., 0]
    else:
        # A fractional supersample: average the big picture down by area.
        def shrink(channel):
            img = Image.fromarray(channel.astype(np.float32), mode="F")
            return np.asarray(img.resize((width, height), Image.Resampling.BOX), dtype=np.float64)

        hdr = np.stack([shrink(hdr[..., c]) for c in range(3)], axis=2)
        depth = shrink(depth)
    shown = develop(hdr, depth, shot.post)
    seed = sum(key.encode())
    picture = grade(shown, shot.post, seed)
    if shot.split:
        # The editing card: as shot on the left, black and white on the right.
        mono = monochrome(shown, shot.post)
        half = width // 2
        picture = np.concatenate([picture[:, :half], mono[:, half:]], axis=1)
    image = Image.fromarray(to_bytes(picture))
    path = out / f"{key}.{fmt}"
    if fmt == "webp":
        image.save(path, "WEBP", quality=82, method=6)
    else:
        image.save(path)
    return f"{path.name}: {width}x{height} in {time.time() - started:.0f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the nude masterclass's pictures (data/library/art/nude_guide)."
    )
    parser.add_argument("--only", nargs="+", metavar="KEY", help="render just these art keys")
    parser.add_argument("--size", type=int, default=540, help="width in pixels (default 540)")
    parser.add_argument(
        "--ss", type=float, default=1.5, help="supersampling per pixel side (default 1.5)"
    )
    parser.add_argument("--out", type=Path, default=OUT, help="where the pictures go")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="small PNGs without supersampling, for looking at a pose",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "scripts"))
    from guide_art.scenes import SCENES

    keys = args.only or list(SCENES)
    unknown = [k for k in keys if k not in SCENES]
    if unknown:
        parser.error(f"no scene for {', '.join(unknown)}")
    size, ss, fmt = (args.size, args.ss, "webp")
    if args.preview:
        size, ss, fmt = (min(args.size, 240), 1, "png")
    args.out.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        jobs = [pool.submit(render_one, k, size, ss, args.out, fmt) for k in keys]
        for job in jobs:
            print(job.result(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
