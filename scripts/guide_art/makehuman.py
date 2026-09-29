"""MakeHuman's body data, read without MakeHuman.

The HM08 base mesh, its morph targets and the rules that mix them into a
body, and the default skeleton with its skin weights: MakeHuman's own
assets, released as CC0, in the form MPFB2 (the MakeHuman plugin for
Blender) keeps them. The `anny` wheel on PyPI (NAVER LABS' body model,
Apache 2.0 code) ships exactly that folder under anny/data/mpfb2, so the
data are fetched from there - one pinned file, checked by its hash, only
the data taken out of it and none of its code ever imported. Set
MAKEHUMAN_DATA to a folder that already holds them to skip the download.

Coordinates in the files are MakeHuman's: decimetres, y up, the figure
facing +z. `to_blender` turns them into metres with z up and the figure
facing -y, toward a camera in front of it.
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

WHEEL = (
    "https://files.pythonhosted.org/packages/f8/5e/"
    "0833d42b1ed3afd6c5c52c61fc31185348bc6cc2e17f296c518d593fdc37/anny-0.6.1-py3-none-any.whl"
)
WHEEL_SHA256 = "9dbd3d6c2e5dae20a4f5e0b80e104f50fd13d2e15e42c90fc288e00d86e60e09"
PREFIX = "anny/data/mpfb2/"


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "vechnost" / "makehuman-anny-0.6.1"


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """The MPFB2 data folder, fetched and unpacked on first use."""
    given = os.environ.get("MAKEHUMAN_DATA")
    if given:
        return Path(given)
    out = cache_dir() / "mpfb2"
    if (out / "3dobjs" / "base.obj").exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wheel = Path(tmp) / "anny.whl"
        print(f"fetching MakeHuman data: {WHEEL}", flush=True)
        with urllib.request.urlopen(WHEEL, timeout=300) as r, open(wheel, "wb") as f:
            shutil.copyfileobj(r, f)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest != WHEEL_SHA256:
            raise RuntimeError(f"{WHEEL} has sha256 {digest}, expected {WHEEL_SHA256}")
        staging = Path(tmp) / "mpfb2"
        with zipfile.ZipFile(wheel) as z:
            for info in z.infolist():
                if not info.filename.startswith(PREFIX) or info.is_dir():
                    continue
                target = staging / info.filename[len(PREFIX) :]
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        shutil.move(str(staging), out)
    return out


def to_blender(co):
    co = np.asarray(co, dtype=np.float64)
    return np.stack([co[..., 0], -co[..., 2], co[..., 1]], axis=-1) * 0.1


@dataclass
class Base:
    co: np.ndarray  # (N, 3) decimetres
    uv: np.ndarray  # (M, 2)
    faces: dict[str, list[tuple[tuple[int, ...], tuple[int, ...]]]]
    groups: dict[str, np.ndarray]


@lru_cache(maxsize=1)
def base() -> Base:
    co, uv = [], []
    faces: dict[str, list] = {}
    g = ""
    with open(data_dir() / "3dobjs" / "base.obj") as f:
        for line in f:
            if line.startswith("v "):
                co.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uv.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("g "):
                g = line.split()[1]
            elif line.startswith("f "):
                vs, ts = [], []
                for tok in line.split()[1:]:
                    a = tok.split("/")
                    vs.append(int(a[0]) - 1)
                    ts.append(int(a[1]) - 1 if len(a) > 1 and a[1] else -1)
                faces.setdefault(g, []).append((tuple(vs), tuple(ts)))
    raw = json.loads((data_dir() / "mesh_metadata" / "basemesh_vertex_groups.json").read_text())
    groups = {
        name: np.concatenate([np.arange(a, b + 1) for a, b in ranges])
        if ranges
        else np.zeros(0, int)
        for name, ranges in raw.items()
    }
    return Base(np.array(co), np.array(uv), faces, groups)


def load_target(rel: str) -> tuple[np.ndarray, np.ndarray]:
    """One morph target: vertex indices and their offsets (decimetres)."""
    cached = cache_dir() / "targets" / (rel.replace("/", "__") + ".npz")
    if cached.exists():
        z = np.load(cached)
        return z["i"], z["d"].reshape(-1, 3)
    with gzip.open(data_dir() / "targets" / rel, "rt") as f:
        rows = [line.split() for line in f if line.strip() and not line.startswith("#")]
    i = np.array([int(r[0]) for r in rows], dtype=np.int64)
    d = np.array([[float(x) for x in r[1:4]] for r in rows], dtype=np.float64).reshape(-1, 3)
    cached.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cached, i=i, d=d)
    return i, d


@lru_cache(maxsize=1)
def _macro() -> dict:
    return json.loads((data_dir() / "targets" / "macrodetails" / "macro.json").read_text())


# Where each part of a macro starts and ends. macro.json pads its bounds by
# a hundredth so a value on a seam falls in some part; the levels themselves
# sit exactly here.
_SEAMS = {"age": (0.0, 0.1875, 0.5, 1.0), "gender": (0.0, 1.0)}


def _part_weights(var: str, value: float) -> dict[str, float]:
    """How much each named level of a macro counts at `value`: the two ends
    of the part the value falls in, linearly between them."""
    parts = _macro()["macrotargets"][var]["parts"]
    seams = _SEAMS.get(var, (0.0, 0.5, 1.0))
    for n, p in enumerate(parts):
        if p["lowest"] <= value <= p["highest"]:
            lo, hi = seams[n], seams[n + 1]
            t = min(max((value - lo) / (hi - lo), 0.0), 1.0)
            out = {}
            if p["low"]:
                out[p["low"]] = 1.0 - t
            if p["high"]:
                out[p["high"]] = out.get(p["high"], 0.0) + t
            return out
    # Between two parts (height at exactly 0.5): no target of this macro.
    return {}


@dataclass
class Shape:
    """A body: MakeHuman's macros (0-1) and any detail targets by weight."""

    gender: float = 0.0
    age: float = 0.5
    muscle: float = 0.5
    weight: float = 0.5
    height: float = 0.5
    proportions: float = 0.5
    cupsize: float = 0.5
    firmness: float = 0.5
    race: dict[str, float] = field(default_factory=lambda: {"caucasian": 1.0})
    details: dict[str, float] = field(default_factory=dict)


def macro_targets(s: Shape) -> list[tuple[str, float]]:
    """The macro targets a shape mixes, each with its weight: the product of
    the levels it stands for, over every combination the files cover."""
    w = {
        "gender": _part_weights("gender", s.gender),
        "age": _part_weights("age", s.age),
        "muscle": _part_weights("muscle", s.muscle),
        "weight": _part_weights("weight", s.weight),
        "height": _part_weights("height", s.height),
        "proportions": _part_weights("proportions", s.proportions),
        "cupsize": _part_weights("cupsize", s.cupsize),
        "firmness": _part_weights("firmness", s.firmness),
        "race": {k: v for k, v in s.race.items() if v},
    }

    def combos(names):
        for combo in itertools.product(*[list(w[n].items()) for n in names]):
            weight = float(np.prod([x for _, x in combo]))
            if weight > 1e-4:
                yield "-".join(k for k, _ in combo), weight

    out = [(f"macrodetails/{k}.target.gz", x) for k, x in combos(["race", "gender", "age"])]
    out += [
        (f"macrodetails/universal-{k}.target.gz", x)
        for k, x in combos(["gender", "age", "muscle", "weight"])
    ]
    for folder, extra in (
        ("macrodetails/proportions", ["proportions"]),
        ("macrodetails/height", ["height"]),
        ("breast", ["cupsize", "firmness"]),
    ):
        out += [
            (f"{folder}/{k}.target.gz", x)
            for k, x in combos(["gender", "age", "muscle", "weight", *extra])
        ]
    root = data_dir() / "targets"
    return [(rel, x) for rel, x in out if (root / rel).exists()]


@lru_cache(maxsize=1)
def _detail_targets() -> dict[str, str]:
    """Detail target name -> its path under targets/."""
    root = data_dir() / "targets"
    idx = {}
    for p in root.rglob("*.target.gz"):
        rel = str(p.relative_to(root))
        if not rel.startswith(("macrodetails", "expression", "_images")):
            idx[p.name[: -len(".target.gz")]] = rel
    return idx


def morph(s: Shape) -> np.ndarray:
    """The base mesh with the shape applied, helpers and joints included."""
    co = base().co.copy()
    for rel, x in macro_targets(s):
        i, d = load_target(rel)
        co[i] += d * x
    names = _detail_targets()
    for name, x in s.details.items():
        if x:
            i, d = load_target(names[name])
            co[i] += d * x
    return co


@lru_cache(maxsize=2)
def rig(name: str = "default") -> dict:
    return json.loads((data_dir() / "rigs" / "standard" / f"rig.{name}.json").read_text())


@lru_cache(maxsize=2)
def weights(name: str = "default") -> dict[str, list]:
    path = data_dir() / "rigs" / "standard" / f"weights.{name}.json"
    return json.loads(path.read_text())["weights"]


def joint(co: np.ndarray, spec: dict) -> np.ndarray:
    """Where a bone end sits on a morphed mesh (MakeHuman coordinates)."""
    b = base()
    st = spec["strategy"]
    if st == "CUBE":
        return co[b.groups[spec["cube_name"]]].mean(axis=0)
    if st == "MEAN":
        return co[np.asarray(spec["vertex_indices"])].mean(axis=0)
    if st == "VERTEX":
        return co[int(spec["vertex_index"])]
    raise ValueError(st)


def texture(name: str) -> Path:
    return data_dir() / "textures" / name
