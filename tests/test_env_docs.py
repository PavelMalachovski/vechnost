"""docs/ENVIRONMENT_VARIABLES.md says what the code reads, and nothing else.

The document used to prescribe API_TOKEN_TELEGRAM, a name no code had read
for months, and to leave out half the settings. Its table is now generated
from `Settings` (scripts/env_docs.py); this holds the committed copy to it,
and holds the hand-written part to every variable the package reads without
going through `Settings`.
"""

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _env_docs():
    spec = importlib.util.spec_from_file_location("env_docs", REPO / "scripts" / "env_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_settings_table_is_what_settings_says():
    env_docs = _env_docs()
    committed = env_docs.DOC.read_text(encoding="utf-8")
    assert env_docs.rendered(committed) == committed, (
        "docs/ENVIRONMENT_VARIABLES.md no longer matches Settings: "
        "run `python scripts/env_docs.py --write` and commit the result"
    )


def test_every_setting_has_a_description():
    """The table's third column is the field's own description."""
    from vechnost_bot.config import Settings

    undescribed = [name for name, field in Settings.model_fields.items() if not field.description]
    assert not undescribed


# `os.getenv("NAME")`, `os.environ.get("NAME")` and `os.environ["NAME"]`.
ENV_READ = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z][A-Z0-9_]+)["']"""
    r"""|os\.environ\[\s*["']([A-Z][A-Z0-9_]+)["']"""
)


def test_every_variable_read_outside_settings_is_documented():
    document = _env_docs().DOC.read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", document))
    read = {
        name
        for path in (REPO / "vechnost_bot").rglob("*.py")
        for pair in ENV_READ.findall(path.read_text(encoding="utf-8"))
        for name in pair
        if name
    }
    assert read, "the scan found nothing to check"
    assert read <= documented, f"read but not documented: {sorted(read - documented)}"
