"""scripts/generate_certificates.py: one code format, and codes stay off git.

The script is not a package, so it is loaded from its path. The database
is an in-memory SQLite, as in test_privacy.py.
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import select

from vechnost_bot.config import settings
from vechnost_bot.payments import database
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.models import Certificate

from .test_no_secrets import CERTIFICATE

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generate_certificates.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_certificates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gen = _load()


@pytest.fixture
def memory_db():
    with (
        patch.object(settings, "database_url", "sqlite+aiosqlite:///:memory:"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def test_mint_writes_codes_to_the_database_and_cards_to_disk(memory_db, tmp_path):
    codes = await gen.mint(3, tmp_path, "some_bot", with_sql=True)

    assert len(codes) == 3 and len(set(codes)) == 3
    async with get_db() as session:
        rows = list((await session.execute(select(Certificate))).scalars().all())
    assert sorted(row.code for row in rows) == sorted(codes)
    assert all(row.is_used is False for row in rows)

    for i, code in enumerate(codes, 1):
        png = tmp_path / f"certificate_{i:02d}_{code}.png"
        assert png.exists()
        with Image.open(png) as image:
            assert image.size[0] > 200 and image.size[1] > image.size[0]

    sql = (tmp_path / "certificates.sql").read_text()
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    for code in codes:
        assert f"('{code}', FALSE, CURRENT_TIMESTAMP) ON CONFLICT (code) DO NOTHING" in sql


async def test_minted_codes_are_what_the_secrets_scan_looks_for(memory_db, tmp_path):
    """The format the script mints and the one test_no_secrets.py guards
    must be the same, or a pasted code slips past the scan - which is how
    the old 4+8 codes did."""
    for code in await gen.mint(5, tmp_path, "some_bot", with_sql=False):
        assert CERTIFICATE.fullmatch(code), code
        assert "XXXX" not in code


def test_activation_link_is_the_bot_deep_link():
    link = gen.activation_link("VECH-ABCD-EFGH", "some_bot")
    assert link == "https://t.me/some_bot?start=activate_VECH-ABCD-EFGH"
    # Telegram accepts only [A-Za-z0-9_-] in a start parameter, 64 chars max.
    param = link.split("?start=")[1]
    assert param.replace("_", "").replace("-", "").isalnum() and len(param) <= 64


def test_the_default_output_directory_is_git_ignored():
    assert gen.DEFAULT_OUT == ROOT / "certificates"
    assert gen.output_dir_is_safe(gen.DEFAULT_OUT)
    assert gen.output_dir_is_safe(ROOT / "certificates_2026")
    assert gen.output_dir_is_safe(ROOT / "certificates" / "batch-1")


def test_an_unignored_directory_inside_the_checkout_is_refused(tmp_path):
    assert not gen.output_dir_is_safe(ROOT / "docs")
    assert not gen.output_dir_is_safe(ROOT / "vouchers")
    assert gen.output_dir_is_safe(tmp_path)

    with pytest.raises(SystemExit):
        gen.parse_args(["3", "--out", str(ROOT / "vouchers"), "--bot", "some_bot"])
    args = gen.parse_args(["3", "--out", str(tmp_path), "--bot", "@some_bot"])
    assert args.bot == "some_bot" and args.count == 3


def test_count_is_bounded():
    with pytest.raises(SystemExit):
        gen.parse_args(["0", "--bot", "some_bot"])
    with pytest.raises(SystemExit):
        gen.parse_args(["101", "--bot", "some_bot"])


def test_sql_quotes_nothing_but_the_code():
    sql = gen.sql_for(["VECH-ABCD-EFGH"])
    assert sql.count("INSERT") == 1
    assert "'VECH-ABCD-EFGH'" in sql
