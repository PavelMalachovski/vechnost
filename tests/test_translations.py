"""Structural checks on the three UI translation files.

These exist because a misplaced block in one YAML file can silently orphan
a key under the wrong parent — `yaml.safe_load` still succeeds, `pytest -q`
stays green, and nothing short of exercising every *actually used* key
notices. Synchronous, no async fixtures: nothing here awaits anything.
"""

import re
from pathlib import Path

import pytest
import yaml

from vechnost_bot.i18n import Language, get_text

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
SOURCE_DIR = REPO_ROOT / "vechnost_bot"
LANGUAGES = [Language.RUSSIAN]

# Matches `get_text('some.key', ...)` / `get_text("some.key", ...)` — a
# literal first argument. Dynamic keys (e.g. `get_text(f'themes.{x}', ...)`)
# don't match and are intentionally out of scope: their key can't be known
# statically.
_GET_TEXT_CALL = re.compile(r"""get_text\(\s*['"]([\w.]+)['"]""")

# Pre-existing and out of scope for this test: `LanguageBackHandler`
# (vechnost_bot/callback_handlers.py) asks for `welcome.title`,
# `welcome.subtitle` and `welcome.prompt`, none of which any translation
# file has ever defined (the real keys are `welcome.greeting_title`,
# `welcome.greeting_subtitle` and `welcome.language_prompt` — confirmed via
# `git show master:data/translations_ru.yaml`, i.e. this predates this
# branch). Excluded here so this test's job — catching *new* breakage —
# isn't lost in an unrelated, already-broken one; tracked separately by
# `test_the_known_language_back_bug_is_still_broken` below so a fix removes
# both the bug and this carve-out in the same change.
_KNOWN_PRE_EXISTING_MISSING_KEYS = {"welcome.title", "welcome.subtitle", "welcome.prompt"}


def _load(language: Language) -> dict:
    path = DATA_DIR / f"translations_{language.value}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _flatten(d: dict, prefix: str = "") -> set[str]:
    """All dotted leaf keys, the same addressing `get_text` uses."""
    keys: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten(v, full)
        else:
            keys.add(full)
    return keys


def _keys_used_in_source() -> set[str]:
    """Every literal dotted key passed to `get_text(...)` anywhere in the bot.

    Reading these off real call sites (rather than off the YAML files being
    tested) is deliberate: a key that a misplaced YAML block moves to a new,
    self-consistent location still "resolves" if you only ever check keys
    the YAML itself claims to have. Checking against the source finds the
    call site — e.g. `handlers.py`'s `get_text('about.cta', language)` — that
    would actually break.
    """
    keys: set[str] = set()
    for path in SOURCE_DIR.rglob("*.py"):
        if "test" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        keys |= set(_GET_TEXT_CALL.findall(text))
    return keys


def test_all_three_files_parse():
    for language in LANGUAGES:
        data = _load(language)
        assert isinstance(data, dict)
        assert data  # not empty


def test_all_three_files_have_identical_key_structure():
    """Catches a language file whose structure diverges from the other two."""
    key_sets = {language: _flatten(_load(language)) for language in LANGUAGES}
    reference_language = LANGUAGES[0]
    reference_keys = key_sets[reference_language]

    for language in LANGUAGES[1:]:
        keys = key_sets[language]
        only_in_reference = reference_keys - keys
        only_in_language = keys - reference_keys
        assert not only_in_reference and not only_in_language, (
            f"{reference_language.value} vs {language.value}: "
            f"only in {reference_language.value}: {sorted(only_in_reference)}; "
            f"only in {language.value}: {sorted(only_in_language)}"
        )


def test_every_key_used_in_source_resolves_in_every_language():
    """The check that catches a key parented under the wrong block.

    A misplaced key still parses, and the YAML file it landed in is still
    internally self-consistent — so a check derived only from the YAML's own
    structure cannot tell the difference. This one can, because it starts
    from what the *code* asks for, not from what the (possibly broken) YAML
    happens to contain: `about.cta` moving under `compat` leaves `about.cta`
    unresolved regardless of where it ended up.
    """
    used_keys = _keys_used_in_source() - _KNOWN_PRE_EXISTING_MISSING_KEYS
    assert used_keys  # sanity: the scan itself must find something

    failures = []
    for language in LANGUAGES:
        for key in sorted(used_keys):
            resolved = get_text(key, language)
            if resolved == key:
                failures.append((key, language.value))

    assert not failures, (
        "these get_text() keys did not resolve (the key came back as-is, "
        "meaning it is missing or nested under the wrong parent): "
        f"{failures}"
    )


@pytest.mark.xfail(strict=True, reason="pre-existing bug, out of scope for this task")
def test_the_known_language_back_bug_is_still_broken():
    """Guards the carve-out above from going stale.

    If `welcome.title`/`welcome.subtitle`/`welcome.prompt` ever start
    resolving, this starts unexpectedly passing (`strict=True` turns that
    into a failure), which is the signal to delete both this test and the
    entry in `_KNOWN_PRE_EXISTING_MISSING_KEYS`.
    """
    for key in sorted(_KNOWN_PRE_EXISTING_MISSING_KEYS):
        assert get_text(key, Language.RUSSIAN) != key
