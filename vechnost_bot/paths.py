"""Where the repository's content lives: data/, assets/ and webapp/.

VECHNOST runs from a checkout of its repository, never from an installed
wheel: the production image copies the checkout's layout rather than
installing the package (Dockerfile), and CI and development install it
editable. The three directories sit next to the package, and every module
finds them here, from the package's own location - never from the working
directory. `Path("data")` read the translations relative to wherever the
process was started, so a bot started anywhere but the repository's root
answered with its keys ("privacy.done") instead of its text, and could draw
no card at all (audit I-28).

A copy of the package without them - a wheel, or `pip install .` - stops
here, on import, and says why, rather than failing later on the first
message somebody sends.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
WEBAPP = ROOT / "webapp"

_missing = [path.name for path in (DATA, ASSETS, WEBAPP) if not path.is_dir()]
if _missing:
    raise RuntimeError(
        f"VECHNOST runs from a checkout of its repository, and {', '.join(_missing)} "
        f"is not next to the package in {ROOT}. Install it editable "
        "(pip install -e .) or put the checkout on PYTHONPATH: a wheel carries the "
        "code without data/, assets/ and webapp/."
    )


def in_repo(path: str | Path) -> Path:
    """A path the content names relative to the repository (assets/backgrounds.yml
    does), made absolute. An absolute path is returned as it is."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path
