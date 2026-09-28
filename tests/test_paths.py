"""The bot finds its content from the package, never from the working
directory (audit I-28).

`Path("data")` in i18n and the relative faces in assets/backgrounds.yml were
read against wherever the process was started. A bot started anywhere but
the repository's root answered with its translation keys ("privacy.done")
instead of its text, and could not draw a single card. The suite itself runs
from the root, where neither can show, so both tests start a fresh
interpreter somewhere else.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vechnost_bot import paths

REPO = Path(__file__).resolve().parent.parent

# Everything the bot and the web process read from the checkout, read from
# a directory that is not the checkout.
FROM_ELSEWHERE = """
from vechnost_bot.compat import load_spheres
from vechnost_bot.daily_card import render_daily_card
from vechnost_bot.i18n import Language, get_text
from vechnost_bot.library import load_guide, load_reflection
from vechnost_bot.logic import localized_game_data
from vechnost_bot.payments.web import ASSETS_DIR, WEBAPP_DIR
from vechnost_bot.renderer import get_background_path, render_card_bytes
from vechnost_bot.steps69 import load_cells
import datetime

assert get_text("privacy.done", Language.RUSSIAN) != "privacy.done", "translations"
assert localized_game_data.get_game_data().themes, "the deck"
assert load_reflection() and load_guide("nude_guide"), "the Library"
assert load_spheres(), "the compatibility test"
assert len(load_cells()) == 69, "the board"
faces = [("acq", 1, "q"), ("couples", 3, "q"), ("sex", 0, "q"), ("sex", 0, "t"), ("prov", 0, "q")]
for face in faces:
    card = render_card_bytes("Привет", get_background_path(*face))
    assert card[:2] == b"\\xff\\xd8", face
image, _ = render_daily_card(datetime.date(2026, 9, 28), Language.RUSSIAN)
assert image.getvalue()[:2] == b"\\xff\\xd8", "the daily card"
assert (ASSETS_DIR / "images" / "vechnost_logo.png").is_file(), "the /start logo"
assert (WEBAPP_DIR / "index.html").is_file() and (ASSETS_DIR / "fonts").is_dir(), "the Mini App"
print("ok")
"""


@pytest.mark.slow
def test_the_bot_reads_its_content_from_any_directory(tmp_path):
    # The checkout's code, not whatever copy of the package is installed;
    # the environment is the suite's (a fake token, a throwaway database).
    result = subprocess.run(
        [sys.executable, "-c", FROM_ELSEWHERE],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip().endswith("ok")
    assert not list(tmp_path.iterdir()), "reading wrote files"


@pytest.mark.slow
def test_a_copy_without_the_content_says_why(tmp_path):
    """What a wheel, or `pip install .`, would install: the code alone. It
    stops on import and names what is missing, rather than failing later on
    the first message somebody sends."""
    shutil.copytree(
        REPO / "vechnost_bot",
        tmp_path / "vechnost_bot",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    result = subprocess.run(
        [sys.executable, "-c", "import vechnost_bot.i18n"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0
    assert "runs from a checkout" in result.stderr
    assert "data, assets, webapp" in result.stderr


def test_the_three_directories_are_the_checkouts():
    assert paths.ROOT == REPO
    assert paths.DATA == REPO / "data" and paths.ASSETS == REPO / "assets"
    assert paths.WEBAPP == REPO / "webapp"


def test_a_path_the_content_names_is_read_in_the_repository():
    assert (
        paths.in_repo("assets/backgrounds/library.png") == REPO / "assets/backgrounds/library.png"
    )
    assert paths.in_repo(paths.ASSETS / "fonts") == paths.ASSETS / "fonts"


def test_without_the_directories_the_module_refuses_to_load(monkeypatch):
    """The same file, run where none of the three is a directory."""
    spec = importlib.util.spec_from_file_location("paths_without_content", paths.__file__)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    with pytest.raises(RuntimeError, match="runs from a checkout") as refused:
        spec.loader.exec_module(module)
    assert "data, assets, webapp" in str(refused.value)
