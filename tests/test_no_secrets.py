"""Nothing that opens a door may be committed.

The repository is public. It once carried a production database URL with
its password, a Tribute API key (which is also the /admin bearer and, now,
the key webhooks are signed with), five live gift-certificate codes and the
Telegram ids, name and handle of real customers - all in docs/ and scripts/,
all for months. Deleting them from the tree is the easy half; this test is
the half that keeps them from coming back.

Scope is the parts of the tree a person writes prose or examples into. The
package and the tests are not scanned for Telegram ids: the fixtures there
are fake by construction, and the two things that matter everywhere - a bot
token and a real database password - are checked on every file.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".json",
    ".sql", ".sh", ".ps1", ".html", ".example", ".mako",
}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", "assets", "fonts", "certificates"}

# Where examples are written by hand and a real value slips in unnoticed.
PROSE_DIRS = ("docs", "scripts", "sql")
PROSE_ROOT_FILES = ("README.md", "CLAUDE.md", "env.example")

# Ids that are plainly made up and may appear in examples.
FAKE_TELEGRAM_IDS = {
    "123456789", "1234567890", "0123456789", "987654321",
    "111111111", "222222222", "333333333", "555555555",
}
PLACEHOLDER_PASSWORDS = {"password", "pass", "secret", "***", "xxx", "changeme"}

BOT_TOKEN = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
DB_URL = re.compile(r"[a-z+]+://[^:/\s@]+:([^@\s]+)@[^\s]+")
TRIBUTE_KEY = re.compile(r"TRIBUTE_API_KEY\s*[=:]\s*['\"]?([0-9a-fA-F][0-9a-fA-F-]{19,})")
CERTIFICATE = re.compile(r"\bVECH-[A-Z2-9]{4}-[A-Z2-9]{4}\b")
TELEGRAM_ID = re.compile(r"(?<![\w.])\d{9,10}(?![\w.])")


def _text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def _prose_files():
    for path in _text_files():
        rel = path.relative_to(ROOT)
        if rel.parts[0] in PROSE_DIRS or str(rel) in PROSE_ROOT_FILES:
            yield path


def _lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return list(enumerate(text.splitlines(), start=1))


def _placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in PLACEHOLDER_PASSWORDS
        or "your" in lowered
        or "example" in lowered
        or "<" in value
        or "${" in value
        or "…" in value
        or len(value) < 8
    )


def test_no_bot_token_anywhere():
    hits = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in _text_files()
        for n, line in _lines(p)
        if BOT_TOKEN.search(line)
    ]
    assert not hits, f"a Telegram bot token is committed: {hits}"


def test_no_database_password_anywhere():
    hits = []
    for p in _text_files():
        for n, line in _lines(p):
            for match in DB_URL.finditer(line):
                if not _placeholder(match.group(1)):
                    hits.append(f"{p.relative_to(ROOT)}:{n}")
    assert not hits, f"a database URL with a real password is committed: {hits}"


def test_no_tribute_api_key_anywhere():
    hits = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in _text_files()
        for n, line in _lines(p)
        if TRIBUTE_KEY.search(line)
    ]
    assert not hits, f"a Tribute API key is committed: {hits}"


def test_no_certificate_codes_in_docs_or_scripts():
    """A code is a bearer token for lifetime access. Only XXXX placeholders."""
    hits = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in _prose_files()
        for n, line in _lines(p)
        for code in CERTIFICATE.findall(line)
        if "XXXX" not in code
    ]
    assert not hits, f"a gift certificate code is committed: {hits}"


def test_no_real_telegram_ids_in_docs_or_scripts():
    """Examples use ids from FAKE_TELEGRAM_IDS; anything else is somebody."""
    hits = [
        f"{p.relative_to(ROOT)}:{n}:{value}"
        for p in _prose_files()
        for n, line in _lines(p)
        for value in TELEGRAM_ID.findall(line)
        if value not in FAKE_TELEGRAM_IDS
    ]
    assert not hits, (
        "a Telegram id that is not a known fake appears in docs or scripts; "
        f"use one from FAKE_TELEGRAM_IDS: {hits}"
    )


def test_the_scan_sees_the_files_it_is_meant_to():
    """A test that scans nothing passes for the wrong reason."""
    names = {str(p.relative_to(ROOT)) for p in _prose_files()}
    assert "env.example" in names
    assert "scripts/README.md" in names
    assert any(name.startswith("docs/") for name in names)
